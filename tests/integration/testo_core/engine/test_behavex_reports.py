"""A real BehaveX stage gets both its own HTML report and Allure results.

BehaveX skips ``report.html`` whenever ``--formatter`` is passed, so the adapter
runs it plain and the executor exports ``report.json`` to Allure afterwards
(:mod:`testo_core.reporting.behavex_allure`). This runs the real ``behavex``
binary on a two-scenario feature, so it fails if either report goes missing.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

from testo_core.config.schema import Stage
from testo_core.engine.executor import run_stage

pytestmark = [pytest.mark.integration, pytest.mark.tier_fast]


def _write_target(repo: Path) -> None:
    steps = repo / "features" / "steps"
    steps.mkdir(parents=True)
    (repo / "features" / "mixed.feature").write_text(
        "Feature: Mixed\n"
        "  Scenario: Passes\n"
        "    Given a step that passes\n"
        "  Scenario: Fails\n"
        "    Given a step that fails\n",
        encoding="utf-8",
    )
    (steps / "steps.py").write_text(
        "from behave import given\n\n"
        "@given('a step that passes')\n"
        "def passes(context):\n"
        "    pass\n\n"
        "@given('a step that fails')\n"
        "def fails(context):\n"
        "    raise AssertionError('boom')\n",
        encoding="utf-8",
    )


def test_behavex_stage_writes_native_html_and_allure_results(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write_target(repo)
    stage = Stage(
        name="flows",
        framework="behavex",
        target_repo=repo,
        args=("features/mixed.feature",),
        workers=1,
    )
    # The ``behavex`` next to this interpreter, whatever PATH the test runner has.
    env = dict(os.environ)
    env["PATH"] = os.pathsep.join([str(Path(sys.executable).parent), env.get("PATH", "")])

    result = run_stage(
        stage, plan_name="demo", artifacts_root=tmp_path / "artifacts", parent_env=env
    )

    assert result.returncode == 1  # one scenario fails on purpose
    assert result.error is None

    stage_dir = tmp_path / "artifacts" / "demo" / "flows"
    run_log = (stage_dir / "run.log").read_text(encoding="utf-8")
    # BehaveX itself rendered the report (it prints this line only without a formatter),
    # so it links each scenario's log; Testo's fallback renderer cannot.
    assert "HTML output report is located at" in run_log
    html = (stage_dir / "behave_reports" / "report.html").read_text(encoding="utf-8")
    assert html.count("scenario.log") >= 2

    results_dir = stage_dir / "allure-results" / "behavex"
    results = [
        json.loads(path.read_text(encoding="utf-8")) for path in results_dir.glob("*-result.json")
    ]
    assert sorted((r["name"], r["status"]) for r in results) == [
        ("Fails", "failed"),
        ("Passes", "passed"),
    ]
    for r in results:
        log_attachments = [a["source"] for a in r["attachments"] if a["name"] == "scenario.log"]
        assert log_attachments and all((results_dir / src).is_file() for src in log_attachments)
    assert "[testo] behavex: exported 2 scenario(s) to Allure" in run_log
