"""Top-level orchestrator: iterate plan stages, emit events, aggregate results.

Sequential by design — see [the refactor plan](../../.cursor/plans).  The
loop here is the *only* place that would need to change to introduce
concurrent stage execution in a future iteration.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import os
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Protocol

from testo_core.config.schema import Plan
from testo_core.engine.events import (
    EngineEvent,
    PlanFinished,
    PlanStarted,
    StageFinished,
    StageStarted,
)
from testo_core.engine.executor import run_stage
from testo_core.engine.exit_codes import classify_exit_code
from testo_core.engine.result import PlanResult, StageResult
from testo_core.reporting.paths import plan_artifacts_dir

logger = logging.getLogger(__name__)


class _EventSink(Protocol):
    """Anything with a ``handle(EngineEvent)`` method qualifies as a renderer."""

    wants_streaming: bool

    def handle(self, event: EngineEvent) -> None: ...


def run_plan(
    plan: Plan,
    *,
    renderer: _EventSink,
    artifacts_root: Path | None = None,
    parent_env: Mapping[str, str] | None = None,
    persist: bool = True,
    fail_fast: bool = False,
) -> PlanResult:
    """Execute every stage in ``plan`` sequentially.

    When *persist* is ``True``, the :mod:`testo_core.persistence` composite
    backend writes ``plan_result.json`` and (when the DB layer is available)
    upserts a :class:`~testo_core.repository.models.RunRecord`.

    When *fail_fast* is ``True``, a stage finishing with a non-zero returncode
    aborts the remaining stages: a ``plan_aborted`` NDJSON event is written
    (see ``docs/CLI Commands/Troubleshooting and Error Codes.md``) before the
    terminal ``plan_finished`` event.
    """
    artifacts_root = (artifacts_root or Path("artifacts")).expanduser().resolve()
    plan_artifacts = plan_artifacts_dir(artifacts_root, plan.name)
    plan_artifacts.mkdir(parents=True, exist_ok=True)
    events_path = plan_artifacts / "events.ndjson"
    parent_env = parent_env if parent_env is not None else dict(os.environ)

    started_at = time.time()
    renderer.handle(PlanStarted(plan=plan))
    stage_results: list[StageResult] = []

    on_chunk = _make_on_chunk(renderer, stream=renderer.wants_streaming)

    with _NdjsonRecorder(events_path) as recorder:
        recorder.write(
            {"event": "plan_started", "plan": plan.name, "stage_count": len(plan.stages)}
        )

        for idx, stage in enumerate(plan.stages, start=1):
            renderer.handle(
                StageStarted(stage=stage, stage_index=idx, stage_count=len(plan.stages))
            )
            recorder.write(
                {
                    "event": "stage_started",
                    "stage": stage.name,
                    "framework": stage.framework,
                    "index": idx,
                    "count": len(plan.stages),
                }
            )

            try:
                stage_result = run_stage(
                    stage,
                    plan_name=plan.name,
                    artifacts_root=artifacts_root,
                    parent_env=parent_env,
                    on_chunk=on_chunk(stage.name),
                )
            except Exception as exc:
                # Broad on purpose: an engine bug becomes an internal-failure result (exit 4)
                # so later stages, persistence and reporters still run.
                logger.exception("stage %s crashed inside the engine", stage.name)
                stage_result = _internal_failure_result(stage=stage, exc=exc)

            stage_results.append(stage_result)
            renderer.handle(StageFinished(result=stage_result))
            recorder.write(
                {
                    "event": "stage_finished",
                    "stage": stage_result.stage_name,
                    "framework": stage_result.framework,
                    "returncode": stage_result.returncode,
                    "duration_s": stage_result.duration_s,
                    "log_path": str(stage_result.log_path) if stage_result.log_path else None,
                    "timed_out": stage_result.timed_out,
                    "error": stage_result.error,
                    "internal_failure": stage_result.internal_failure,
                }
            )

            if fail_fast and stage_result.returncode != 0:
                recorder.write(
                    {
                        "event": "plan_aborted",
                        "plan": plan.name,
                        "reason": "fail_fast",
                        "completed_stages": idx,
                    }
                )
                break

        finished_at = time.time()
        rcs = [s.returncode for s in stage_results]
        exit_code = classify_exit_code(
            rcs,
            infra_error=None,
            internal_failure=any(s.internal_failure for s in stage_results),
        )
        target_repos = {s.target_repo for s in stage_results if s.target_repo is not None}
        target_repo = next(iter(target_repos)) if len(target_repos) == 1 else None
        plan_result = PlanResult(
            plan_name=plan.name,
            started_at=started_at,
            finished_at=finished_at,
            duration_s=finished_at - started_at,
            stages=tuple(stage_results),
            aggregate_returncode=max(rcs, default=0),
            exit_code=exit_code,
            target_repo=target_repo,
        )

        recorder.write(
            {
                "event": "plan_finished",
                "plan": plan_result.plan_name,
                "aggregate_returncode": plan_result.aggregate_returncode,
                "exit_code": int(plan_result.exit_code),
                "duration_s": plan_result.duration_s,
            }
        )

    renderer.handle(PlanFinished(result=plan_result))

    if persist:
        from testo_core.persistence import composite_backend

        backend = composite_backend(artifacts_root=artifacts_root)
        run_id = backend.persist(plan_result)
        if run_id:
            plan_result = dataclasses.replace(
                plan_result, extra={**plan_result.extra, "run_id": run_id}
            )

    return plan_result


def _make_on_chunk(renderer: _EventSink, *, stream: bool):
    """Build a per-stage chunk callback for the executor.

    When streaming, every byte goes through :class:`StageOutputChunk`; the
    renderer prints to the terminal as bytes arrive.  When buffered, the
    callback is a no-op (the log buffer still tees to disk).
    """
    if not stream:

        def _no_op(stage_name: str):  # noqa: ARG001
            return None

        return _no_op

    from testo_core.engine.events import StageOutputChunk

    def factory(stage_name: str):
        def cb(chunk: bytes) -> None:
            renderer.handle(StageOutputChunk(stage_name=stage_name, chunk=chunk))

        return cb

    return factory


class _NdjsonRecorder:
    """Append-only NDJSON file (one event per line)."""

    def __init__(self, path: Path) -> None:
        self._path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = path.open("a", encoding="utf-8")

    def write(self, payload: dict[str, object]) -> None:
        self._fh.write(json.dumps(payload, separators=(",", ":"), ensure_ascii=True))
        self._fh.write("\n")
        self._fh.flush()

    def close(self) -> None:
        try:
            self._fh.flush()
            self._fh.close()
        except OSError:  # pragma: no cover
            pass

    def __enter__(self) -> _NdjsonRecorder:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


def _internal_failure_result(*, stage, exc: Exception) -> StageResult:  # type: ignore[no-untyped-def]
    now = time.time()
    return StageResult(
        stage_name=stage.name,
        framework=stage.framework,
        tier=stage.tier,
        returncode=4,
        started_at=now,
        finished_at=now,
        duration_s=0.0,
        log_path=None,
        artifacts_dir=Path("."),
        command=(),
        output_tail="",
        timed_out=False,
        error=f"internal error: {exc}",
        internal_failure=True,
    )
