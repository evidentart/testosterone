"""A run as a short chat alert: a Slack or Microsoft Teams incoming-webhook message.

The alert says what a developer needs without opening anything: did the cycle
pass, which tests fail, what regressed or got fixed since the previous run, and
which tests just became flaky. It is built from the same stored run records as
``testo report markdown`` (:mod:`testo_core.services.run_summary_markdown`), so
it can be sent for any recorded run: by the ``slack`` / ``teams`` reporters
right after ``testo run``, or later by ``testo notify``.

Webhook URLs are secrets. They come from the environment (or a ``${env:...}``
reporter option), never from a command-line flag, and are never printed.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Literal

import requests

from testo_core.services.flaky_service import FlakyTest, newly_flaky_tests
from testo_core.services.run_summary_markdown import RunSummary, load_run_summary

AlertChannel = Literal["slack", "teams"]
AlertWhen = Literal["failure", "change", "always"]

CHANNELS: tuple[AlertChannel, ...] = ("slack", "teams")
WHEN_CHOICES: tuple[AlertWhen, ...] = ("failure", "change", "always")
WEBHOOK_ENV: dict[AlertChannel, str] = {
    "slack": "TESTO_SLACK_WEBHOOK_URL",
    "teams": "TESTO_TEAMS_WEBHOOK_URL",
}
MAX_NAMES = 10
_TIMEOUT_S = 15


class AlertError(RuntimeError):
    """A webhook rejected the alert or could not be reached."""


@dataclass(frozen=True)
class RunAlert:
    summary: RunSummary
    newly_flaky: tuple[FlakyTest, ...] = ()

    @property
    def ok(self) -> bool:
        return self.summary.run.returncode == 0

    def names(self, kind: str) -> list[str]:
        """Tests whose change since the previous run is ``kind`` (``regression``, ``fix``)."""
        return [c.name for c in self.summary.changes if c.kind == kind]


def load_alert(*, cycle: str | None = None, run_id: str | None = None) -> RunAlert | None:
    """The alert for ``run_id``, or ``cycle``'s latest run; ``None`` when there is no such run."""
    summary = load_run_summary(cycle=cycle, run_id=run_id)
    if summary is None:
        return None
    run = summary.run
    flaky = newly_flaky_tests(cycle=run.cycle, run_id=run.run_id) if run.cycle else ()
    return RunAlert(summary=summary, newly_flaky=flaky)


def should_send(alert: RunAlert, when: AlertWhen) -> bool:
    """``failure``: red run or a newly flaky test. ``change``: anything differs from last run."""
    if when == "always":
        return True
    if when == "failure":
        return not alert.ok or bool(alert.newly_flaky)
    previous = alert.summary.previous
    flipped = (previous.returncode == 0) != alert.ok if previous is not None else not alert.ok
    return flipped or bool(alert.names("regression") or alert.names("fix") or alert.newly_flaky)


def webhook_from_env(channel: AlertChannel, env: dict[str, str] | None = None) -> str:
    return ((env if env is not None else os.environ).get(WEBHOOK_ENV[channel]) or "").strip()


def _title(alert: RunAlert, title: str | None) -> str:
    name = title or alert.summary.run.cycle or "run"
    return f"{'✅' if alert.ok else '❌'} Testosterone: {name} {'passed' if alert.ok else 'failed'}"


def _counts(alert: RunAlert) -> str:
    run = alert.summary.run
    seconds = f"{run.wall_duration_ms / 1000:.1f}s"
    if run.total_tests is None:
        return f"Ran in {seconds}"
    failed = (run.failed or 0) + (run.broken or 0)
    return f"{run.passed or 0} passed · {failed} failed · {run.skipped or 0} skipped in {seconds}"


def _sections(alert: RunAlert) -> list[tuple[str, list[str]]]:
    """(heading, test names) for every non-empty list, most urgent first."""
    sections = [
        ("New regressions", alert.names("regression")),
        ("Newly flaky", [t.name for t in alert.newly_flaky]),
        ("Failing", list(alert.summary.failing)),
        ("Fixed", alert.names("fix")),
    ]
    return [(heading, names) for heading, names in sections if names]


def _clip(names: list[str]) -> list[str]:
    extra = len(names) - MAX_NAMES
    return names[:MAX_NAMES] + ([f"… and {extra} more"] if extra > 0 else [])


def _slack_escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def slack_payload(
    alert: RunAlert, *, title: str | None = None, run_url: str | None = None
) -> dict[str, Any]:
    """Slack incoming-webhook body (Block Kit, with a plain ``text`` fallback for notifications)."""
    heading = _title(alert, title)
    blocks: list[dict[str, Any]] = [
        {"type": "header", "text": {"type": "plain_text", "text": heading[:150], "emoji": True}},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*{_counts(alert)}*"}},
    ]
    for label, names in _sections(alert):
        lines = "\n".join(f"• `{_slack_escape(n)}`" for n in _clip(names))
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*{label} ({len(names)})*\n{lines}"[:3000]},
            }
        )
    context = f"Run `{alert.summary.run.run_id}`"
    if run_url:
        context += f" · <{run_url}|View run>"
    blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": context}]})
    return {"text": f"{heading}: {_counts(alert)}", "blocks": blocks}


def teams_payload(
    alert: RunAlert, *, title: str | None = None, run_url: str | None = None
) -> dict[str, Any]:
    """Teams Workflows webhook body: one Adaptive Card (v1.4) in a ``message`` envelope."""
    body: list[dict[str, Any]] = [
        {
            "type": "TextBlock",
            "text": _title(alert, title),
            "weight": "Bolder",
            "size": "Large",
            "color": "Good" if alert.ok else "Attention",
            "wrap": True,
        },
        {"type": "TextBlock", "text": _counts(alert), "wrap": True, "spacing": "Small"},
    ]
    for label, names in _sections(alert):
        body.append({"type": "TextBlock", "text": f"**{label} ({len(names)})**", "wrap": True})
        body.append(
            {"type": "TextBlock", "text": "\n".join(f"- {n}" for n in _clip(names)), "wrap": True}
        )
    body.append(
        {
            "type": "TextBlock",
            "text": f"Run {alert.summary.run.run_id}",
            "isSubtle": True,
            "size": "Small",
        }
    )
    card: dict[str, Any] = {
        "type": "AdaptiveCard",
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "version": "1.4",
        "body": body,
    }
    if run_url:
        card["actions"] = [{"type": "Action.OpenUrl", "title": "View run", "url": run_url}]
    return {
        "type": "message",
        "attachments": [
            {"contentType": "application/vnd.microsoft.card.adaptive", "content": card}
        ],
    }


def build_payload(
    channel: AlertChannel, alert: RunAlert, *, title: str | None = None, run_url: str | None = None
) -> dict[str, Any]:
    builder = slack_payload if channel == "slack" else teams_payload
    return builder(alert, title=title, run_url=run_url)


def post(url: str, payload: dict[str, Any]) -> None:
    """POST ``payload`` to a webhook. Errors never include the URL, which is a secret."""
    try:
        resp = requests.post(url, json=payload, timeout=_TIMEOUT_S)
    except requests.RequestException as exc:
        raise AlertError(f"webhook unreachable ({type(exc).__name__})") from None
    if resp.status_code >= 400:
        raise AlertError(f"webhook answered HTTP {resp.status_code}: {resp.text[:200]}")
