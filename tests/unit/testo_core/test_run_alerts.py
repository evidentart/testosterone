"""Slack and Teams alerts for a recorded run (testo_core/services/run_alerts.py)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import requests
from typer.testing import CliRunner

from testo_core.cli.app import app
from testo_core.history.views import CompletedRunView
from testo_core.reporting.collector import CollectedResults
from testo_core.reporting.reporters.alert_reporter import SlackReporter, TeamsReporter
from testo_core.reporting.reporters.base import ReportContext
from testo_core.repository.models import RunStatus
from testo_core.services import flaky_service, run_alerts
from testo_core.services import run_summary_markdown as md
from testo_core.services.flaky_service import FlakyTest
from testo_core.services.report_archive_diff import CaseChange

URL = "https://hooks.example/secret-token"


def _run(run_id: str, *, created_at: float, returncode: int = 0) -> CompletedRunView:
    return CompletedRunView(
        run_id=run_id,
        status=RunStatus.COMPLETED,
        created_at=created_at,
        started_at=created_at,
        finished_at=created_at + 1,
        test_kind="cycle",
        returncode=returncode,
        wall_duration_ms=4200.0,
        metrics_duration_ms=None,
        total_tests=3,
        passed=2,
        failed=1 if returncode else 0,
        broken=0,
        skipped=0,
        avg_case_ms=None,
        health_pct=None,
        target_repo=None,
        snapshot_dir=f"static/history/{run_id}/artifacts",
        audit_json=None,
        cycle="api",
    )


def _change(name: str, kind: str) -> CaseChange:
    before, after = ("passed", "failed") if kind == "regression" else ("failed", "passed")
    return CaseChange(
        key=name,
        name=name,
        group="g",
        baseline_status=before,
        current_status=after,
        kind=kind,  # type: ignore[arg-type]
        duration_delta_ms=None,
    )


def _flaky(name: str) -> FlakyTest:
    return FlakyTest(
        key=name,
        name=name,
        group="g",
        runs=3,
        passed=2,
        failed=1,
        flips=2,
        flip_rate=1.0,
        last_status="passed",
        history=("passed", "failed", "passed"),
    )


def _alert(
    *,
    returncode: int = 0,
    previous_returncode: int | None = 0,
    failing: tuple[str, ...] = (),
    changes: tuple[CaseChange, ...] = (),
    newly_flaky: tuple[FlakyTest, ...] = (),
) -> run_alerts.RunAlert:
    previous = (
        _run("old", created_at=1, returncode=previous_returncode)
        if previous_returncode is not None
        else None
    )
    summary = md.RunSummary(
        run=_run("new", created_at=2, returncode=returncode),
        previous=previous,
        failing=failing,
        changes=changes,
    )
    return run_alerts.RunAlert(summary=summary, newly_flaky=newly_flaky)


@pytest.mark.parametrize(
    ("alert", "expected"),
    [
        (_alert(), {"failure": False, "change": False, "always": True}),
        (_alert(returncode=1, failing=("t",)), {"failure": True, "change": True, "always": True}),
        # Still red, nothing new: "change" stays quiet, "failure" keeps reminding.
        (
            _alert(returncode=1, previous_returncode=1, failing=("t",)),
            {"failure": True, "change": False, "always": True},
        ),
        (
            _alert(previous_returncode=1, changes=(_change("t", "fix"),)),
            {"failure": False, "change": True, "always": True},
        ),
        (_alert(newly_flaky=(_flaky("t"),)), {"failure": True, "change": True, "always": True}),
        (
            _alert(previous_returncode=None, returncode=1),
            {"failure": True, "change": True, "always": True},
        ),
    ],
)
def test_should_send(alert: run_alerts.RunAlert, expected: dict[str, bool]) -> None:
    assert {w: run_alerts.should_send(alert, w) for w in run_alerts.WHEN_CHOICES} == expected


def test_slack_payload_lists_what_needs_attention_first() -> None:
    alert = _alert(
        returncode=1,
        failing=("test_a", "test_<b>"),
        changes=(_change("test_a", "regression"), _change("test_c", "fix")),
        newly_flaky=(_flaky("test_f"),),
    )
    payload = run_alerts.slack_payload(alert, run_url="https://ci/run/1")

    assert payload["text"] == (
        "❌ Testosterone: api failed: 2 passed · 1 failed · 0 skipped in 4.2s"
    )
    sections = [b["text"]["text"] for b in payload["blocks"] if b["type"] == "section"]
    assert sections[1:] == [
        "*New regressions (1)*\n• `test_a`",
        "*Newly flaky (1)*\n• `test_f`",
        "*Failing (2)*\n• `test_a`\n• `test_&lt;b&gt;`",
        "*Fixed (1)*\n• `test_c`",
    ]
    assert "<https://ci/run/1|View run>" in payload["blocks"][-1]["elements"][0]["text"]


def test_long_lists_are_clipped() -> None:
    names = tuple(f"test_{i:02}" for i in range(13))
    payload = run_alerts.slack_payload(_alert(returncode=1, failing=names))
    failing = payload["blocks"][2]["text"]["text"]
    assert failing.startswith("*Failing (13)*")
    assert failing.endswith("• `… and 3 more`")


def test_teams_payload_is_an_adaptive_card_message() -> None:
    alert = _alert(returncode=1, failing=("test_a",))
    payload = run_alerts.teams_payload(alert, title="Nightly", run_url="https://ci/run/1")

    assert payload["type"] == "message"
    card = payload["attachments"][0]["content"]
    assert card["type"] == "AdaptiveCard"
    texts = [b["text"] for b in card["body"]]
    assert texts[0] == "❌ Testosterone: Nightly failed"
    assert "**Failing (1)**" in texts and "- test_a" in texts
    assert card["actions"][0]["url"] == "https://ci/run/1"


class _Response:
    def __init__(self, status: int, text: str = "") -> None:
        self.status_code, self.text = status, text


def test_post_errors_never_contain_the_webhook_url(monkeypatch: pytest.MonkeyPatch) -> None:
    def unreachable(url: str, **_: Any) -> None:
        raise requests.ConnectionError(f"cannot reach {url}")

    monkeypatch.setattr(run_alerts.requests, "post", unreachable)
    with pytest.raises(run_alerts.AlertError) as exc:
        run_alerts.post(URL, {})
    assert "secret-token" not in str(exc.value)

    monkeypatch.setattr(run_alerts.requests, "post", lambda *_, **__: _Response(404, "no_team"))
    with pytest.raises(run_alerts.AlertError, match="HTTP 404: no_team"):
        run_alerts.post(URL, {})


@pytest.fixture
def recorded(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> list[tuple[str, dict]]:
    """Two recorded runs of cycle ``api``; the newest regressed ``test_a``. Captures posts."""
    runs = [_run("new", created_at=2, returncode=1), _run("old", created_at=1)]
    for run, statuses in zip(
        runs,
        [{"test_a": "failed", "test_b": "passed"}, {"test_a": "passed", "test_b": "passed"}],
        strict=True,
    ):
        folder = tmp_path / str(run.snapshot_dir) / "unit" / "allure-results" / "pytest"
        folder.mkdir(parents=True)
        for name, status in statuses.items():
            (folder / f"{name}-result.json").write_text(
                json.dumps({"historyId": name, "name": name, "status": status}), encoding="utf-8"
            )
    for module in (md, flaky_service):
        monkeypatch.setattr(module.paths, "ORCHESTRATOR_ROOT", tmp_path)
        monkeypatch.setattr(module, "list_recent_runs", lambda *, limit: runs)
    monkeypatch.setattr(
        md, "get_run", lambda *, run_id: next(r for r in runs if r.run_id == run_id)
    )

    sent: list[tuple[str, dict]] = []
    monkeypatch.setattr(run_alerts, "post", lambda url, payload: sent.append((url, payload)))
    return sent


def test_load_alert_reads_the_run_history(recorded: list[tuple[str, dict]]) -> None:
    alert = run_alerts.load_alert(cycle="api")
    assert alert is not None
    assert alert.summary.failing == ("test_a",)
    assert alert.names("regression") == ["test_a"]
    assert alert.newly_flaky == ()


def _publish(reporter: SlackReporter | TeamsReporter, run_id: str | None = "new") -> Any:
    context = ReportContext(artifacts_root=Path("."), plan_name="api", run_id=run_id)
    return reporter.publish(results=CollectedResults(artifacts_root=Path(".")), context=context)


def test_slack_reporter_posts_to_the_configured_webhook(recorded: list[tuple[str, dict]]) -> None:
    outcome = _publish(SlackReporter(options={"webhook": URL, "title": "API"}))
    assert outcome.ok and outcome.message == "Slack alert sent."
    url, payload = recorded[0]
    assert url == URL
    assert payload["blocks"][0]["text"]["text"] == "❌ Testosterone: API failed"


def test_teams_reporter_reads_the_webhook_from_the_environment(
    recorded: list[tuple[str, dict]], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("TESTO_TEAMS_WEBHOOK_URL", raising=False)
    assert not _publish(TeamsReporter()).ok
    assert recorded == []

    monkeypatch.setenv("TESTO_TEAMS_WEBHOOK_URL", URL)
    assert _publish(TeamsReporter()).ok
    assert recorded[0][1]["type"] == "message"


def test_reporter_stays_quiet_when_there_is_nothing_to_report(
    recorded: list[tuple[str, dict]],
) -> None:
    outcome = _publish(SlackReporter(options={"webhook": URL}), run_id="old")  # green, first run
    assert outcome.ok and "nothing to report" in outcome.message
    assert recorded == []


def test_reporter_needs_a_recorded_run(recorded: list[tuple[str, dict]]) -> None:
    outcome = _publish(SlackReporter(options={"webhook": URL}), run_id=None)
    assert not outcome.ok and "recorded run" in outcome.message


def test_notify_cli_dry_run_prints_both_payloads(recorded: list[tuple[str, dict]]) -> None:
    result = CliRunner().invoke(
        app, ["notify", "--to", "slack", "--to", "teams", "--cycle", "api", "--dry-run"]
    )
    assert result.exit_code == 0, result.output
    assert '"slack": {' in result.output and '"teams": {' in result.output
    assert recorded == []


def test_notify_cli_sends_and_needs_the_env_var(
    recorded: list[tuple[str, dict]], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("TESTO_SLACK_WEBHOOK_URL", raising=False)
    missing = CliRunner().invoke(app, ["notify", "--to", "slack", "--cycle", "api"])
    assert missing.exit_code == 2
    assert "TESTO_SLACK_WEBHOOK_URL" in missing.output

    monkeypatch.setenv("TESTO_SLACK_WEBHOOK_URL", URL)
    sent = CliRunner().invoke(app, ["notify", "--to", "slack", "--cycle", "api"])
    assert sent.exit_code == 0, sent.output
    assert [url for url, _ in recorded] == [URL]


def test_notify_cli_rejects_unknown_channels(recorded: list[tuple[str, dict]]) -> None:
    result = CliRunner().invoke(app, ["notify", "--to", "discord", "--cycle", "api"])
    assert result.exit_code == 2


def test_notify_cli_reports_a_failed_post(
    recorded: list[tuple[str, dict]], monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(url: str, payload: dict) -> None:
        raise run_alerts.AlertError("webhook answered HTTP 500: oops")

    monkeypatch.setattr(run_alerts, "post", fail)
    monkeypatch.setenv("TESTO_SLACK_WEBHOOK_URL", URL)
    result = CliRunner().invoke(app, ["notify", "--to", "slack", "--cycle", "api"])
    assert result.exit_code == 3
    assert "HTTP 500" in result.output and "secret-token" not in result.output
