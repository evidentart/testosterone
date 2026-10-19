"""Flaky test detection over a cycle's run history (testo_core/services/flaky_service.py)."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from testo_core.history.views import CompletedRunView
from testo_core.repository.models import RunStatus
from testo_core.services import flaky_service


def _run(run_id: str, *, cycle: str = "unit", created_at: float = 1.0) -> CompletedRunView:
    return CompletedRunView(
        run_id=run_id,
        status=RunStatus.COMPLETED,
        created_at=created_at,
        started_at=created_at,
        finished_at=created_at + 1,
        test_kind="cycle",
        returncode=0,
        wall_duration_ms=1000.0,
        metrics_duration_ms=None,
        total_tests=None,
        passed=None,
        failed=None,
        broken=None,
        skipped=None,
        avg_case_ms=None,
        health_pct=None,
        target_repo=None,
        snapshot_dir=f"static/history/{run_id}/artifacts",
        audit_json=None,
        cycle=cycle,
    )


def _write_results(root: Path, run: CompletedRunView, statuses: dict[str, str]) -> None:
    folder = root / str(run.snapshot_dir) / "unit" / "allure-results" / "pytest"
    folder.mkdir(parents=True, exist_ok=True)
    for name, status in statuses.items():
        (folder / f"{name}-result.json").write_text(
            json.dumps(
                {"historyId": name, "name": name, "fullName": f"tests.m.{name}", "status": status}
            ),
            encoding="utf-8",
        )


@pytest.mark.parametrize(
    ("statuses", "flaky"),
    [
        (["passed", "failed", "passed"], True),
        (["passed", "broken", "passed", "failed"], True),
        (["passed", "passed", "failed"], False),  # one flip: a regression, not flakiness
        (["failed", "failed", "failed"], False),
        (["passed", "skipped", "passed"], False),  # skipped runs don't count
        (["passed", "skipped", "failed", "skipped", "passed"], True),
    ],
)
def test_classify(statuses: list[str], flaky: bool) -> None:
    result = flaky_service.classify("k", [{"status": s, "name": "t"} for s in statuses])
    assert (result is not None) is flaky


def test_classify_scores_flip_rate_and_keeps_history() -> None:
    result = flaky_service.classify(
        "k", [{"status": s, "name": "test_x", "group": "m"} for s in ["passed", "failed", "passed"]]
    )
    assert result is not None
    assert (result.passed, result.failed, result.flips, result.flip_rate) == (2, 1, 2, 1.0)
    assert result.history == ("passed", "failed", "passed")
    assert result.last_status == "passed"


def test_find_flaky_tests_reads_each_runs_snapshot(monkeypatch, tmp_path: Path) -> None:  # noqa: ANN001
    # list_recent_runs returns newest first; another cycle's run is ignored.
    runs = [
        _run("r3", created_at=3),
        _run("other", cycle="nightly", created_at=2.5),
        _run("r2", created_at=2),
        _run("r1", created_at=1),
    ]
    _write_results(
        tmp_path, runs[3], {"test_flaky": "passed", "test_ok": "passed", "test_broke": "passed"}
    )
    _write_results(
        tmp_path, runs[2], {"test_flaky": "failed", "test_ok": "passed", "test_broke": "passed"}
    )
    _write_results(
        tmp_path, runs[0], {"test_flaky": "passed", "test_ok": "passed", "test_broke": "failed"}
    )
    _write_results(tmp_path, runs[1], {"test_flaky": "failed"})

    monkeypatch.setattr(flaky_service.paths, "ORCHESTRATOR_ROOT", tmp_path)
    monkeypatch.setattr(flaky_service, "list_recent_runs", lambda *, limit: runs)

    report = flaky_service.find_flaky_tests(cycle="unit")

    assert (report.runs_analyzed, report.tests_analyzed) == (3, 3)
    assert [t.name for t in report.flaky] == ["test_flaky"]
    assert report.flaky[0].history == ("passed", "failed", "passed")


def test_find_flaky_tests_limits_to_the_window(monkeypatch, tmp_path: Path) -> None:  # noqa: ANN001
    runs = [_run(f"r{i}", created_at=i) for i in range(5, 0, -1)]  # newest first
    for run, status in zip(runs, ["passed", "passed", "failed", "passed", "failed"], strict=True):
        _write_results(tmp_path, run, {"test_x": status})
    monkeypatch.setattr(flaky_service.paths, "ORCHESTRATOR_ROOT", tmp_path)
    monkeypatch.setattr(flaky_service, "list_recent_runs", lambda *, limit: runs)

    # Last 2 runs: passed, passed. Not flaky. All 5: failed, passed, failed, passed, passed.
    assert flaky_service.find_flaky_tests(cycle="unit", window=2).flaky == ()
    assert len(flaky_service.find_flaky_tests(cycle="unit", window=5).flaky) == 1


def test_runs_without_a_snapshot_are_skipped(monkeypatch, tmp_path: Path) -> None:  # noqa: ANN001
    runs = [replace(_run("r1"), snapshot_dir=None)]
    monkeypatch.setattr(flaky_service, "list_recent_runs", lambda *, limit: runs)
    report = flaky_service.find_flaky_tests(cycle="unit")
    assert (report.runs_analyzed, report.flaky) == (0, ())
