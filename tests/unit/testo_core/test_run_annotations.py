"""Failing tests as GitHub Actions annotations (testo_core/services/run_annotations.py)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from testo_core.cli.app import app
from testo_core.history.views import CompletedRunView
from testo_core.repository.models import RunStatus
from testo_core.services import run_annotations as ann
from testo_core.services import run_summary_markdown as md

PYTEST_TRACE = (
    "def test_bad():\n>       helper(1)\n\ntests/test_x.py:5: \n_ _ _\n\n"
    "    def helper(x):\n>       assert x == 2\nE       AssertionError\n\n"
    "tests/test_x.py:2: AssertionError"
)
PYTHON_TRACE = (
    'Traceback (most recent call last):\n  File "/usr/lib/python3/site.py", line 9, in run\n'
    '  File "features/steps/api.py", line 14, in step_impl\n    assert False\nAssertionError'
)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    (tmp_path / "app" / "tests").mkdir(parents=True)
    (tmp_path / "app" / "tests" / "test_x.py").write_text("x", encoding="utf-8")
    (tmp_path / "features" / "steps").mkdir(parents=True)
    (tmp_path / "features" / "steps" / "api.py").write_text("x", encoding="utf-8")
    return tmp_path


def test_locate_takes_the_first_frame_inside_the_workspace(repo: Path) -> None:
    # pytest paths are relative to the stage's target_repo (here app/).
    assert ann.locate(PYTEST_TRACE, workspace=repo, roots=[repo, repo / "app"]) == (
        "app/tests/test_x.py",
        5,
    )
    # Frames outside the workspace (the standard library) are skipped.
    assert ann.locate(PYTHON_TRACE, workspace=repo, roots=[repo]) == ("features/steps/api.py", 14)
    assert ann.locate("no frames here", workspace=repo, roots=[repo]) is None
    assert ann.locate(PYTEST_TRACE, workspace=repo, roots=[repo]) is None  # not found from root


def test_workflow_commands_escape_and_cap_at_the_limit() -> None:
    failures = [
        ann.Failure(
            name="test_a", status="failed", message="50% off\nline 2", file="a,b.py", line=3
        ),
        ann.Failure(name="test_b", status="broken", message="boom"),
        ann.Failure(name="test_c", status="failed", message="x"),
    ]
    lines = ann.workflow_commands(failures, cycle="api", limit=2)
    assert lines == [
        "::error file=a%2Cb.py,line=3,title=test_a failed (api)::50%25 off%0Aline 2",
        "::error title=test_b broken (api)::boom",
        "::notice title=testo::1 more failing tests are not annotated; the job summary lists "
        "them all",
    ]


def _run(snapshot: str) -> CompletedRunView:
    return CompletedRunView(
        run_id="r1",
        status=RunStatus.FAILED,
        created_at=1,
        started_at=1,
        finished_at=2,
        test_kind="cycle",
        returncode=1,
        wall_duration_ms=1000.0,
        metrics_duration_ms=None,
        total_tests=2,
        passed=1,
        failed=1,
        broken=0,
        skipped=0,
        avg_case_ms=None,
        health_pct=None,
        target_repo=None,
        snapshot_dir=snapshot,
        audit_json=None,
        cycle="api",
    )


def test_report_annotations_cli(
    repo: Path, tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path_factory.mktemp("orchestrator")
    run = _run("static/history/r1/artifacts")
    folder = root / str(run.snapshot_dir) / "unit" / "allure-results" / "pytest"
    folder.mkdir(parents=True)
    results = {
        "test_bad": {
            "status": "failed",
            "statusDetails": {"message": "AssertionError", "trace": PYTEST_TRACE},
        },
        "test_ok": {"status": "passed"},
    }
    for name, data in results.items():
        (folder / f"{name}-result.json").write_text(
            json.dumps({"historyId": name, "name": name, **data}), encoding="utf-8"
        )
    (repo / "testosterone.yaml").write_text(
        "version: 1\ncycles:\n  api:\n    stages:\n"
        "      - name: unit\n        equipment: pytest\n        target_repo: app\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(ann.paths, "ORCHESTRATOR_ROOT", root)
    monkeypatch.setattr(md.paths, "ORCHESTRATOR_ROOT", root)
    monkeypatch.setattr(md, "list_recent_runs", lambda *, limit: [run])
    monkeypatch.chdir(repo)

    result = CliRunner().invoke(app, ["report", "annotations", "--cycle", "api"])
    assert result.exit_code == 0, result.output
    assert result.output == (
        "::error file=app/tests/test_x.py,line=5,title=test_bad failed (api)::AssertionError\n"
    )
