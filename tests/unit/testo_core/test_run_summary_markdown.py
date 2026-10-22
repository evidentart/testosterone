"""A run rendered as Markdown for job summaries and PR comments."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest
from typer.testing import CliRunner

from testo_core.cli.app import app
from testo_core.history.views import CompletedRunView
from testo_core.repository.models import RunStatus
from testo_core.services import run_summary_markdown as md


def _run(run_id: str, *, created_at: float, returncode: int = 0) -> CompletedRunView:
    return CompletedRunView(
        run_id=run_id,
        status=RunStatus.COMPLETED,
        created_at=created_at,
        started_at=created_at,
        finished_at=created_at + 1,
        test_kind="cycle",
        returncode=returncode,
        wall_duration_ms=12300.0,
        metrics_duration_ms=None,
        total_tests=3,
        passed=2,
        failed=1,
        broken=0,
        skipped=0,
        avg_case_ms=None,
        health_pct=66.7,
        target_repo=None,
        snapshot_dir=f"static/history/{run_id}/artifacts",
        audit_json=None,
        cycle="unit",
        stage_health=[
            {
                "name": "unit",
                "framework": "pytest",
                "returncode": returncode,
                "duration_s": 1.5,
                "total_tests": 3,
                "passed": 2,
                "failed": 1,
                "broken": 0,
                "skipped": 0,
            }
        ],
    )


def _write(root: Path, run: CompletedRunView, statuses: dict[str, str]) -> None:
    folder = root / str(run.snapshot_dir) / "unit" / "allure-results" / "pytest"
    folder.mkdir(parents=True, exist_ok=True)
    for name, status in statuses.items():
        (folder / f"{name}-result.json").write_text(
            json.dumps({"historyId": name, "name": name, "status": status}), encoding="utf-8"
        )


@pytest.fixture
def two_runs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> list[CompletedRunView]:
    runs = [_run("new", created_at=2, returncode=1), _run("old", created_at=1)]  # newest first
    _write(tmp_path, runs[1], {"test_a": "passed", "test_b": "passed"})
    _write(tmp_path, runs[0], {"test_a": "failed", "test_b": "passed", "test_c": "passed"})
    monkeypatch.setattr(md.paths, "ORCHESTRATOR_ROOT", tmp_path)
    monkeypatch.setattr(md, "list_recent_runs", lambda *, limit: runs)
    monkeypatch.setattr(
        md, "get_run", lambda *, run_id: next(r for r in runs if r.run_id == run_id)
    )
    return runs


def test_latest_run_of_a_cycle_against_the_one_before(two_runs: list[CompletedRunView]) -> None:
    summary = md.load_run_summary(cycle="unit")
    assert summary is not None
    assert (summary.run.run_id, summary.previous and summary.previous.run_id) == ("new", "old")
    assert summary.failing == ("test_a",)
    assert [(c.kind, c.name) for c in summary.changes] == [
        ("regression", "test_a"),
        ("added", "test_c"),
    ]


def test_a_specific_run_finds_its_own_previous_run(two_runs: list[CompletedRunView]) -> None:
    summary = md.load_run_summary(run_id="old")
    assert summary is not None and summary.previous is None


def test_markdown_starts_with_the_comment_marker(two_runs: list[CompletedRunView]) -> None:
    summary = md.load_run_summary(cycle="unit")
    assert summary is not None
    text = md.render_markdown(summary, run_url="https://ci/run/1")

    assert text.splitlines()[0] == md.comment_marker("unit") == "<!-- testo-summary:unit -->"
    assert "### ❌ Testosterone: `unit` failed" in text
    assert "**2 passed · 1 failed · 0 skipped** in 12.3s · health 66.7%" in text
    assert "| unit | pytest | ❌ fail | 3 | 2 | 1 | 0 | 1.5s |" in text
    assert "- `test_a`" in text
    assert "**Since the previous run:** 1 regression, 1 new test" in text
    assert "[workflow run](https://ci/run/1)" in text


def test_first_run_says_there_is_nothing_to_compare(two_runs: list[CompletedRunView]) -> None:
    summary = md.load_run_summary(run_id="old")
    assert summary is not None
    assert "First recorded run of this cycle" in md.render_markdown(summary)


def test_pipes_in_test_names_do_not_break_the_table(two_runs: list[CompletedRunView]) -> None:
    summary = md.load_run_summary(cycle="unit")
    assert summary is not None
    renamed = replace(summary.changes[0], name="test[a|b]")
    text = md.render_markdown(replace(summary, changes=(renamed,)))
    assert "`test[a\\|b]`" in text


def test_cli_prints_and_writes(two_runs: list[CompletedRunView], tmp_path: Path) -> None:
    runner = CliRunner()
    printed = runner.invoke(app, ["report", "markdown", "--cycle", "unit"])
    assert printed.exit_code == 0, printed.stdout
    assert printed.stdout.startswith("<!-- testo-summary:unit -->")

    out = tmp_path / "summary.md"
    written = runner.invoke(app, ["report", "markdown", "--cycle", "unit", "--out", str(out)])
    assert written.exit_code == 0
    assert out.read_text(encoding="utf-8") == printed.stdout


def test_cli_without_runs_is_invalid_input(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(md, "list_recent_runs", lambda *, limit: [])
    assert CliRunner().invoke(app, ["report", "markdown", "--cycle", "nope"]).exit_code == 2


def test_quarantined_failures_are_labelled(two_runs: list[CompletedRunView]) -> None:
    summary = md.load_run_summary(cycle="unit")
    assert summary is not None
    stage = {**summary.run.stage_health[0], "returncode": 0, "quarantined": ["test_a"]}
    text = md.render_markdown(
        replace(summary, run=replace(summary.run, returncode=0, stage_health=[stage]))
    )
    assert "| unit | pytest | ✅ pass · 1 quarantined |" in text
    assert "- `test_a` _(quarantined)_" in text
