"""Unit tests for ``run_plan`` lifecycle & state (QA Strategies LC/ST rows).

Complements ``test_orchestrator.py`` (fail-fast rows): full ``events.ndjson``
contract, renderer event sequence, streaming chunk fan-out, persistence
hand-off (``plan_result.json``), and the internal-failure path (EC-04).
Most tests stub the executor; targeted regressions also run real subprocesses.
"""

from __future__ import annotations

import json
import sys
import time
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import pytest

import testo_core.persistence
from testo_core.config.loader import discover_and_load
from testo_core.config.resolver import resolve_plan, resolve_stages_for_plan
from testo_core.config.schema import Plan, Stage
from testo_core.engine import orchestrator
from testo_core.engine.events import (
    EngineEvent,
    PlanFinished,
    PlanStarted,
    StageFinished,
    StageOutputChunk,
    StageStarted,
)
from testo_core.engine.exit_codes import EngineExitCode
from testo_core.engine.result import PlanResult, StageResult
from testo_core.persistence.json_backend import JsonBackend
from tests.fixtures.engine import read_artifact_events, stage_spec, use_echo_adapter, write_config

pytestmark = [pytest.mark.unit, pytest.mark.tier_fast]


class _RecordingRenderer:
    wants_streaming = False

    def __init__(self) -> None:
        self.events: list[EngineEvent] = []

    def handle(self, event: EngineEvent) -> None:
        self.events.append(event)


class _StreamingRenderer(_RecordingRenderer):
    wants_streaming = True


def _stage(name: str) -> Stage:
    return Stage(name=name, framework="pytest", target_repo=Path("."))


def _plan(*names: str, plan_name: str = "lifecycle-plan") -> Plan:
    return Plan(name=plan_name, description=None, stages=tuple(_stage(n) for n in names))


def _result(
    stage: Stage, *, returncode: int = 0, timed_out: bool = False, error: str | None = None
) -> StageResult:
    now = time.time()
    return StageResult(
        stage_name=stage.name,
        framework=stage.framework,
        returncode=returncode,
        started_at=now,
        finished_at=now,
        duration_s=0.1,
        log_path=Path(f"/tmp/{stage.name}.log"),
        artifacts_dir=Path("."),
        command=("pytest",),
        output_tail="",
        timed_out=timed_out,
        error=error,
        target_repo=stage.target_repo.expanduser().resolve(),
    )


def _stub_executor(
    monkeypatch: pytest.MonkeyPatch,
    make_result: Callable[[Stage], StageResult],
) -> None:
    def fake_run_stage(stage: Stage, *, on_chunk=None, **_: object) -> StageResult:
        return make_result(stage)

    monkeypatch.setattr(orchestrator, "run_stage", fake_run_stage)


def test_events_ndjson_full_lifecycle_and_field_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = _plan("lint", "unit")
    _stub_executor(monkeypatch, _result)

    orchestrator.run_plan(
        plan, renderer=_RecordingRenderer(), artifacts_root=tmp_path, persist=False
    )

    events = read_artifact_events(tmp_path, plan.name)
    assert [e["event"] for e in events] == [
        "plan_started",
        "stage_started",
        "stage_finished",
        "stage_started",
        "stage_finished",
        "plan_finished",
    ]

    assert events[0] == {"event": "plan_started", "plan": plan.name, "stage_count": 2}
    assert events[1] == {
        "event": "stage_started",
        "stage": "lint",
        "framework": "pytest",
        "index": 1,
        "count": 2,
    }
    finished = events[2]
    assert finished["returncode"] == 0
    assert finished["timed_out"] is False
    assert finished["error"] is None
    assert finished["internal_failure"] is False
    assert finished["log_path"].endswith("lint.log")
    assert events[-1]["event"] == "plan_finished"
    assert events[-1]["exit_code"] == 0
    assert events[-1]["aggregate_returncode"] == 0


def test_artifact_mirror_includes_error_on_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # ST: the artifact events.ndjson carries `error` even though CIRenderer
    # stdout omits it on stage_finished.
    plan = _plan("hang")
    _stub_executor(
        monkeypatch,
        lambda stage: _result(
            stage, returncode=124, timed_out=True, error="stage exceeded timeout_s=0.5"
        ),
    )

    result = orchestrator.run_plan(
        plan, renderer=_RecordingRenderer(), artifacts_root=tmp_path, persist=False
    )

    assert result.exit_code is EngineExitCode.INFRA_FAILURE
    finished = [
        e for e in read_artifact_events(tmp_path, plan.name) if e["event"] == "stage_finished"
    ][0]
    assert finished["timed_out"] is True
    assert finished["returncode"] == 124
    assert finished["error"] == "stage exceeded timeout_s=0.5"


def test_renderer_receives_ordered_engine_events(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = _plan("lint", "unit")
    _stub_executor(monkeypatch, _result)
    renderer = _RecordingRenderer()

    orchestrator.run_plan(plan, renderer=renderer, artifacts_root=tmp_path, persist=False)

    assert [type(e) for e in renderer.events] == [
        PlanStarted,
        StageStarted,
        StageFinished,
        StageStarted,
        StageFinished,
        PlanFinished,
    ]
    assert isinstance(renderer.events[0], PlanStarted) and renderer.events[0].plan is plan
    stage_started = renderer.events[1]
    assert isinstance(stage_started, StageStarted)
    assert (stage_started.stage_index, stage_started.stage_count) == (1, 2)


def test_streaming_renderer_gets_stage_output_chunks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = _plan("stream-stage")
    renderer = _StreamingRenderer()

    def fake_run_stage(stage: Stage, *, on_chunk=None, **_: object) -> StageResult:
        assert on_chunk is not None, "streaming renderer must produce a chunk callback"
        on_chunk(b"live-bytes")
        return _result(stage)

    monkeypatch.setattr(orchestrator, "run_stage", fake_run_stage)

    orchestrator.run_plan(plan, renderer=renderer, artifacts_root=tmp_path, persist=False)

    chunks = [e for e in renderer.events if isinstance(e, StageOutputChunk)]
    assert chunks == [StageOutputChunk(stage_name="stream-stage", chunk=b"live-bytes")]


def test_buffered_renderer_gets_no_chunk_callback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = _plan("buffered-stage")
    seen_callbacks: list[object] = []

    def fake_run_stage(stage: Stage, *, on_chunk=None, **_: object) -> StageResult:
        seen_callbacks.append(on_chunk)
        return _result(stage)

    monkeypatch.setattr(orchestrator, "run_stage", fake_run_stage)

    orchestrator.run_plan(
        plan, renderer=_RecordingRenderer(), artifacts_root=tmp_path, persist=False
    )

    assert seen_callbacks == [None]


def test_internal_failure_yields_exit_code_4(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # EC-04: an exception escaping the executor is converted into a synthetic
    # rc=4 stage result with internal_failure=True, classifying as 4.
    plan = _plan("kaboom")

    def exploding_run_stage(stage: Stage, **_: object) -> StageResult:
        raise RuntimeError("adapter blew up")

    monkeypatch.setattr(orchestrator, "run_stage", exploding_run_stage)
    renderer = _RecordingRenderer()

    result = orchestrator.run_plan(plan, renderer=renderer, artifacts_root=tmp_path, persist=False)

    assert result.exit_code is EngineExitCode.INTERNAL_ERROR
    assert result.stages[0].returncode == 4
    assert result.stages[0].internal_failure is True
    assert result.target_repo is None
    assert "adapter blew up" in (result.stages[0].error or "")

    finished = [
        e for e in read_artifact_events(tmp_path, plan.name) if e["event"] == "stage_finished"
    ][0]
    assert finished["internal_failure"] is True
    plan_finished = read_artifact_events(tmp_path, plan.name)[-1]
    assert plan_finished["exit_code"] == 4


@pytest.mark.parametrize(
    ("override", "expected"),
    [(None, "default_repo"), ("override_repo", "override_repo")],
)
def test_run_target_repo_comes_from_loaded_stage_default_or_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, override: str | None, expected: str
) -> None:
    (tmp_path / "default_repo").mkdir()
    (tmp_path / "override_repo").mkdir()
    stage = stage_spec("api")
    if override is not None:
        stage["target_repo"] = override
    config_path = write_config(
        tmp_path,
        {
            "version": 1,
            "defaults": {"target_repo": "default_repo"},
            "cycles": {"smoke": {"stages": [stage]}},
        },
    )
    cfg = discover_and_load(config_path=config_path)
    plan = resolve_plan(cfg, plan_name="smoke")
    effective_plan = replace(plan, stages=resolve_stages_for_plan(plan))
    use_echo_adapter(monkeypatch)

    result = orchestrator.run_plan(
        effective_plan, renderer=_RecordingRenderer(), artifacts_root=tmp_path, persist=False
    )

    assert result.target_repo == (tmp_path / expected).resolve()
    assert result.stages[0].target_repo == result.target_repo


def test_run_target_repo_uses_same_resolved_path_for_all_stages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    plan = replace(
        _plan("api", "ui"),
        stages=(
            replace(_stage("api"), target_repo=repo),
            replace(_stage("ui"), target_repo=repo / ".." / "repo"),
        ),
    )
    _stub_executor(monkeypatch, _result)

    result = orchestrator.run_plan(
        plan, renderer=_RecordingRenderer(), artifacts_root=tmp_path, persist=False
    )

    assert result.target_repo == repo.resolve()


def test_run_target_repo_is_none_for_different_repositories(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "api").mkdir()
    (tmp_path / "ui").mkdir()
    plan = replace(
        _plan("api", "ui"),
        stages=(
            replace(_stage("api"), target_repo=tmp_path / "api"),
            replace(_stage("ui"), target_repo=tmp_path / "ui"),
        ),
    )
    _stub_executor(monkeypatch, _result)

    result = orchestrator.run_plan(
        plan, renderer=_RecordingRenderer(), artifacts_root=tmp_path, persist=False
    )

    assert result.target_repo is None


def test_fail_fast_ignores_unattempted_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = tmp_path / "first"
    first.mkdir()
    plan = replace(
        _plan("first", "never-ran"),
        stages=(
            replace(_stage("first"), target_repo=first),
            replace(_stage("never-ran"), target_repo=tmp_path / "other"),
        ),
    )
    _stub_executor(monkeypatch, lambda stage: _result(stage, returncode=1))

    result = orchestrator.run_plan(
        plan,
        renderer=_RecordingRenderer(),
        artifacts_root=tmp_path,
        persist=False,
        fail_fast=True,
    )

    assert len(result.stages) == 1
    assert result.target_repo == first


def test_unresolvable_target_preserves_terminal_lifecycle_and_persistence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    loop = tmp_path / "loop"
    original_resolve = Path.resolve

    def resolve_target(self: Path, strict: bool = False) -> Path:
        if self == loop:
            raise RuntimeError("Symlink loop from 'loop'")
        return original_resolve(self, strict=strict)

    plan = Plan(
        name="broken-target",
        description=None,
        stages=(
            Stage(
                name="broken",
                framework="command",
                target_repo=loop,
                args=(sys.executable, "-c", "pass"),
            ),
        ),
    )
    renderer = _RecordingRenderer()
    monkeypatch.setattr(
        testo_core.persistence,
        "composite_backend",
        lambda *, artifacts_root: JsonBackend(artifacts_root),
    )

    # Non-strict resolve no longer raises for symlink loops on Python 3.13.
    # Fail only this target; artifact paths must still resolve normally.
    with monkeypatch.context() as patch:
        patch.setattr(Path, "resolve", resolve_target)
        result = orchestrator.run_plan(plan, renderer=renderer, artifacts_root=tmp_path)

    assert result.exit_code is EngineExitCode.INTERNAL_ERROR
    assert result.stages[0].internal_failure
    assert "Symlink loop" in (result.stages[0].error or "")
    assert result.stages[0].target_repo is None
    assert result.target_repo is None
    assert isinstance(renderer.events[-1], PlanFinished)
    assert read_artifact_events(tmp_path, plan.name)[-1]["event"] == "plan_finished"
    payload = json.loads((tmp_path / plan.name / "plan_result.json").read_text())
    assert payload["target_repo"] is None
    assert payload["exit_code"] == 4


def test_symlink_change_after_execution_does_not_change_persisted_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    link = tmp_path / "repo"
    link.symlink_to(first, target_is_directory=True)
    plan = Plan(
        name="moving-target",
        description=None,
        stages=(
            Stage(
                name="cwd",
                framework="command",
                target_repo=link,
                args=(sys.executable, "-c", "import os; print(os.getcwd())"),
            ),
        ),
    )

    class _RetargetingRenderer(_RecordingRenderer):
        def handle(self, event: EngineEvent) -> None:
            super().handle(event)
            if isinstance(event, StageFinished):
                link.unlink()
                link.symlink_to(second, target_is_directory=True)

    monkeypatch.setattr(
        testo_core.persistence,
        "composite_backend",
        lambda *, artifacts_root: JsonBackend(artifacts_root),
    )

    result = orchestrator.run_plan(plan, renderer=_RetargetingRenderer(), artifacts_root=tmp_path)

    assert result.exit_code is EngineExitCode.SUCCESS
    assert result.stages[0].output_tail.strip() == str(first)
    assert result.stages[0].target_repo == first
    assert result.target_repo == first
    assert link.resolve() == second
    payload = json.loads((tmp_path / plan.name / "plan_result.json").read_text())
    assert payload["target_repo"] == str(first)


def test_run_target_repo_is_none_without_stages(tmp_path: Path) -> None:
    result = orchestrator.run_plan(
        _plan(), renderer=_RecordingRenderer(), artifacts_root=tmp_path, persist=False
    )

    assert result.target_repo is None


def test_persist_true_hands_result_to_composite_backend(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = _plan("persisted")
    _stub_executor(monkeypatch, _result)
    persisted: list[PlanResult] = []

    class _Backend:
        def persist(self, result: PlanResult) -> None:
            persisted.append(result)

    monkeypatch.setattr(
        testo_core.persistence, "composite_backend", lambda *, artifacts_root: _Backend()
    )

    result = orchestrator.run_plan(
        plan, renderer=_RecordingRenderer(), artifacts_root=tmp_path, persist=True
    )

    assert persisted == [result]


def test_persist_attaches_run_id_from_backend_to_result_extra(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = _plan("with-run-id")
    _stub_executor(monkeypatch, _result)

    class _Backend:
        def persist(self, result: PlanResult) -> str | None:
            return "db-run-id-42"

    monkeypatch.setattr(
        testo_core.persistence, "composite_backend", lambda *, artifacts_root: _Backend()
    )

    result = orchestrator.run_plan(
        plan, renderer=_RecordingRenderer(), artifacts_root=tmp_path, persist=True
    )

    assert result.extra["run_id"] == "db-run-id-42"


def test_persist_leaves_extra_unset_when_backend_returns_no_run_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = _plan("no-run-id")
    _stub_executor(monkeypatch, _result)

    class _Backend:
        def persist(self, result: PlanResult) -> str | None:
            return None

    monkeypatch.setattr(
        testo_core.persistence, "composite_backend", lambda *, artifacts_root: _Backend()
    )

    result = orchestrator.run_plan(
        plan, renderer=_RecordingRenderer(), artifacts_root=tmp_path, persist=True
    )

    assert "run_id" not in result.extra


def test_persist_false_writes_no_plan_result_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = _plan("unpersisted")
    _stub_executor(monkeypatch, _result)

    orchestrator.run_plan(
        plan, renderer=_RecordingRenderer(), artifacts_root=tmp_path, persist=False
    )

    assert not (tmp_path / plan.name / "plan_result.json").exists()


def test_json_backend_writes_plan_result_schema(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # LC: plan_result.json is the durable summary next to events.ndjson.
    plan = _plan("json-plan", plan_name="json-plan-cycle")
    _stub_executor(monkeypatch, lambda stage: _result(stage, returncode=1))

    result = orchestrator.run_plan(
        plan, renderer=_RecordingRenderer(), artifacts_root=tmp_path, persist=False
    )
    JsonBackend(tmp_path).persist(result)

    payload = json.loads((tmp_path / plan.name / "plan_result.json").read_text(encoding="utf-8"))
    assert payload["plan"] == plan.name
    assert payload["exit_code"] == 1
    assert payload["aggregate_returncode"] == 1
    assert payload["stages"][0]["name"] == "json-plan"
    assert payload["stages"][0]["returncode"] == 1
    assert set(payload["stages"][0]) >= {
        "framework",
        "duration_s",
        "log_path",
        "timed_out",
        "error",
    }
