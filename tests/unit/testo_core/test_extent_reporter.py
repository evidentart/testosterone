"""ExtentReporter Jinja dashboard tests."""

from __future__ import annotations

import json
from pathlib import Path

from testo_core.reporting.allure_results import parse_collected_results
from testo_core.reporting.collector import CollectedResults, StageCollection
from testo_core.reporting.reporters.base import ReportContext
from testo_core.reporting.reporters.extent_builder import render_dashboard
from testo_core.reporting.reporters.extent_reporter import ExtentReporter


def _fixture_results(tmp_path: Path) -> CollectedResults:
    stage_dir = tmp_path / "plan-a" / "stage1" / "allure-results" / "pytest"
    stage_dir.mkdir(parents=True)
    (stage_dir / "t1-result.json").write_text(
        json.dumps({"name": "test_alpha", "status": "passed", "start": 1000, "stop": 1500}),
        encoding="utf-8",
    )
    (stage_dir / "t2-result.json").write_text(
        json.dumps(
            {
                "name": "test_beta",
                "status": "failed",
                "start": 2000,
                "stop": 3000,
                "statusDetails": {"message": "assertion error"},
            }
        ),
        encoding="utf-8",
    )
    return CollectedResults(
        artifacts_root=tmp_path,
        stages=[
            StageCollection(
                plan="plan-a",
                stage="stage1",
                framework="pytest",
                results_dir=stage_dir,
                log_path=None,
            )
        ],
    )


def test_render_dashboard_dark_theme_and_tests(tmp_path: Path) -> None:
    results = _fixture_results(tmp_path)
    aggregate = parse_collected_results(results)
    out = tmp_path / "extent-out"
    ctx = ReportContext(artifacts_root=tmp_path, plan_name="plan-a")
    index = render_dashboard(aggregate, context=ctx, output_dir=out)
    html = index.read_text(encoding="utf-8")
    assert 'class="dark"' in html
    assert "test_alpha" in html
    assert "test_beta" in html
    assert "assertion error" in html
    assert "data-stage" in html
    assert "Total" in html


def test_extent_reporter_publish(tmp_path: Path) -> None:
    results = _fixture_results(tmp_path)
    reporter = ExtentReporter(options={"output_dir": str(tmp_path / "reports" / "extent")})
    ctx = ReportContext(artifacts_root=tmp_path, plan_name="plan-a")
    outcome = reporter.publish(results=results, context=ctx)
    assert outcome.ok
    assert (tmp_path / "reports" / "extent" / "index.html").is_file()
