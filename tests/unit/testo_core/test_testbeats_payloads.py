"""TestBeats Slack / Teams payload builders."""

from __future__ import annotations

from testo_core.reporting.allure_results import RunAggregate, StageSummary, TestCaseRecord
from testo_core.reporting.reporters.base import ReportContext
from testo_core.reporting.reporters.testbeats_payloads import (
    ACCENT_GREEN,
    ACCENT_RED,
    accent_color,
    build_slack_payload,
    build_teams_payload,
)


def _aggregate(*, failed: int = 0, broken: int = 0) -> RunAggregate:
    stage = StageSummary(
        plan="p",
        stage="s",
        framework="pytest",
        total=2,
        passed=2 - failed - broken,
        failed=failed,
        broken=broken,
        skipped=0,
        duration_ms=1000,
    )
    tests = (
        TestCaseRecord(
            id="1",
            name="t1",
            full_name="t1",
            status="passed" if failed == 0 else "failed",
            duration_ms=500,
            plan="p",
            stage="s",
            framework="pytest",
            description=None,
            failure_message=None,
            start_ms=1000,
            stop_ms=1500,
        ),
    )
    return RunAggregate(
        artifacts_root="/tmp",
        total=2,
        passed=2 - failed - broken,
        failed=failed,
        broken=broken,
        skipped=0,
        duration_ms=1000,
        stages=(stage,),
        tests=tests,
    )


def test_accent_green_when_no_failures() -> None:
    assert accent_color(_aggregate()) == ACCENT_GREEN


def test_accent_red_when_failed() -> None:
    assert accent_color(_aggregate(failed=1)) == ACCENT_RED


def test_slack_payload_has_blocks_and_color() -> None:
    ctx = ReportContext(artifacts_root="/tmp", plan_name="smoke")
    payload = build_slack_payload(_aggregate(), context=ctx)
    assert "blocks" in payload
    assert payload["attachments"][0]["color"] == ACCENT_GREEN
    assert payload["blocks"][0]["type"] == "header"


def test_teams_payload_adaptive_card() -> None:
    ctx = ReportContext(artifacts_root="/tmp", plan_name="smoke")
    payload = build_teams_payload(_aggregate(failed=1), context=ctx)
    assert payload["type"] == "message"
    att = payload["attachments"][0]
    assert att["contentType"] == "application/vnd.microsoft.card.adaptive"
    card = att["content"]
    assert card["type"] == "AdaptiveCard"
    assert card["version"] == "1.4"
