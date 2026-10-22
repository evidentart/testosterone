"""Playwright JSON reports: retries, flaky tests and attachments, through ingest and ``testo run``.

``tests/fixtures/playwright/results.json`` is a real Playwright 1.64 JSON report
(retries: 1, trace: retain-on-failure) with its paths rewritten to
``/ci/work/app``, as if it had been downloaded from a CI job.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from testo_core.config.schema import Stage
from testo_core.engine.executor import run_stage
from testo_core.reporting.junit_import import import_junit_reports
from testo_core.reporting.playwright_import import playwright_results_for_file
from testo_core.services.cycle_run import junit_ingest_plan

pytestmark = [pytest.mark.unit, pytest.mark.tier_fast]

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "playwright" / "results.json"
TRACED = (
    "tests-demo-slow-api",
    "tests-demo-slow-api-retry1",
    "tests-demo-checkout-flaky-once-api",
    "tests-demo-checkout-always-fails-api",
    "tests-demo-checkout-always-fails-api-retry1",
)


def _repo(tmp_path: Path, *, with_files: bool = True) -> Path:
    repo = tmp_path / "repo"
    (repo / "out").mkdir(parents=True)
    shutil.copy(FIXTURE, repo / "out" / "results.json")
    if with_files:
        for name in TRACED:
            folder = repo / "test-results" / name
            folder.mkdir(parents=True)
            (folder / "trace.zip").write_bytes(b"PK trace " + name.encode())
            (folder / "error-context.md").write_text("# context", encoding="utf-8")
    return repo


def _by_name(results_dir: Path) -> dict[str, dict]:
    out = {}
    for path in results_dir.glob("*-result.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        out[data["name"]] = data
    return out


def test_one_result_per_test_with_retries_as_steps(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    results_dir = tmp_path / "results"

    imported = import_junit_reports(
        target_repo=repo, patterns=("out/*.json",), results_dir=results_dir, tool="e2e"
    )

    assert (imported.tests, imported.failed, imported.flaky) == (5, 2, 1)
    assert imported.errors == ()
    tests = _by_name(results_dir)
    assert {name: t["status"] for name, t in tests.items()} == {
        "passes": "passed",
        "flaky once": "passed",
        "always fails": "failed",
        "slow": "failed",
        "skipped one": "skipped",
    }

    flaky = tests["flaky once"]
    assert flaky["statusDetails"]["flaky"] is True
    assert flaky["statusDetails"]["message"].startswith("Passed on retry. Error: expect(")
    assert [(s["name"], s["status"]) for s in flaky["steps"]] == [
        ("Attempt 1", "failed"),
        ("Attempt 2", "passed"),
    ]
    assert flaky["fullName"] == "tests/demo.spec.ts › checkout › flaky once [api]"
    assert {"name": "subSuite", "value": "checkout"} in flaky["labels"]
    assert {"name": "project", "value": "api"} in flaky["parameters"]
    assert {"name": "attempts", "value": "2"} in flaky["parameters"]

    failed = tests["always fails"]
    # ANSI colour codes from Playwright's error output are stripped.
    assert (
        failed["statusDetails"]["message"]
        == "Error: expect(received).toBe(expected) // Object.is equality"
    )
    assert "\x1b" not in failed["statusDetails"]["trace"]
    assert "demo.spec.ts:8:17" in failed["statusDetails"]["trace"]
    assert tests["skipped one"]["statusDetails"]["message"] == "not today"
    # A timeout is a failure, like Playwright reports it.
    assert tests["slow"]["steps"][0]["statusDetails"]["message"].startswith("Test timeout")


def test_attachments_are_copied_from_the_report_root(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    results_dir = tmp_path / "results"

    imported = import_junit_reports(
        target_repo=repo, patterns=("out/results.json",), results_dir=results_dir
    )

    # 5 traces + 5 error-context files found by path tail, 2 inline testInfo.attach() bodies.
    assert imported.attachments == 12
    failed = _by_name(results_dir)["always fails"]
    last = failed["attachments"]
    assert [a["name"] for a in last] == ["note", "error-context", "trace"]
    trace = next(a for a in last if a["name"] == "trace")
    assert trace["type"] == "application/zip" and trace["source"].endswith("-attachment.zip")
    assert (results_dir / trace["source"]).read_bytes() == (
        b"PK trace tests-demo-checkout-always-fails-api-retry1"
    )
    note = next(a for a in last if a["name"] == "note")
    assert (results_dir / note["source"]).read_text(encoding="utf-8") == "hello"
    # Each attempt keeps its own trace.
    first_trace = next(a for a in failed["steps"][0]["attachments"] if a["name"] == "trace")
    assert (results_dir / first_trace["source"]).read_bytes().endswith(b"always-fails-api")


def test_missing_and_outside_attachments_are_skipped_not_fatal(tmp_path: Path) -> None:
    repo = _repo(tmp_path, with_files=False)
    secret = tmp_path / "secret.txt"
    secret.write_text("do not copy", encoding="utf-8")
    report = json.loads((repo / "out" / "results.json").read_text(encoding="utf-8"))
    attempt = report["suites"][0]["suites"][0]["specs"][0]["tests"][0]["results"][0]
    attempt["attachments"] = [{"name": "leak", "contentType": "text/plain", "path": str(secret)}]
    (repo / "out" / "results.json").write_text(json.dumps(report), encoding="utf-8")
    results_dir = tmp_path / "results"

    imported = import_junit_reports(
        target_repo=repo, patterns=("out/results.json",), results_dir=results_dir
    )

    assert imported.tests == 5
    assert imported.attachments == 2  # only the inline bodies
    assert any("leak: secret.txt not found" in e for e in imported.errors)
    assert any("trace.zip not found" in e for e in imported.errors)
    assert not any(p.read_bytes() == b"do not copy" for p in results_dir.glob("*-attachment*"))


def test_oversized_attachment_is_skipped(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    parsed = playwright_results_for_file(
        repo / "out" / "results.json",
        tool="e2e",
        results_dir=tmp_path / "results",
        attachments_root=repo,
        max_attachment_bytes=4,
    )
    assert parsed.attachments == 0
    assert any("over the size limit" in n for n in parsed.notes)


@pytest.mark.parametrize(
    ("content", "message"),
    [("{not json", "not valid JSON"), ('{"config": {}}', "not a Playwright JSON report")],
)
def test_bad_json_is_reported_and_skipped(tmp_path: Path, content: str, message: str) -> None:
    (tmp_path / "bad.json").write_text(content, encoding="utf-8")
    imported = import_junit_reports(
        target_repo=tmp_path, patterns=("*.json",), results_dir=tmp_path / "results"
    )
    assert imported.tests == 0
    assert message in imported.errors[0]


def test_ingest_stage_records_playwright_json(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    plan = junit_ingest_plan(cycle="web", reports=["out/results.json"], target_repo=repo)

    result = run_stage(plan.stages[0], plan_name=plan.name, artifacts_root=tmp_path / "artifacts")

    assert result.returncode == 1
    log = result.log_path.read_text(encoding="utf-8")  # type: ignore[union-attr]
    assert "recorded 5 test(s), 2 failed, 1 flaky, 12 attachment(s), from 1 file(s)" in log


def test_playwright_stage_prefers_json_over_junit(tmp_path: Path) -> None:
    """Both reports written by one run: only the JSON one is counted."""
    repo = _repo(tmp_path)
    shutil.move(repo / "out" / "results.json", repo / "test-results" / "testo-results.json")
    (repo / "test-results" / "testo-junit.xml").write_text(
        '<testsuite name="x"><testcase name="dup"/></testsuite>', encoding="utf-8"
    )
    stage = Stage(name="web", framework="playwright", target_repo=repo, tier="e2e")
    results_dir = tmp_path / "results"

    imported = import_junit_reports(
        target_repo=repo,
        patterns=("test-results/testo-results.json", "test-results/testo-junit.xml"),
        results_dir=results_dir,
        tool=stage.name,
        first_match_only=True,
    )

    assert imported.tests == 5
    assert "dup" not in _by_name(results_dir)
