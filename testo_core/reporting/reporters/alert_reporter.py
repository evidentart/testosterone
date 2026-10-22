"""``slack`` and ``teams`` reporters: a chat alert after a cycle that needs attention.

Options (all optional)::

    reporters:
      - type: slack
        webhook: ${env:SLACK_WEBHOOK_URL}   # default: $TESTO_SLACK_WEBHOOK_URL
        when: failure                        # failure | change | always
        title: Nightly API tests             # default: the cycle name
        report_url: https://ci.example/123   # "View run" link

The message comes from the run history (:mod:`testo_core.services.run_alerts`),
so it needs the run to be recorded; ``testo run --no-persist`` skips it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from testo_core.reporting.collector import CollectedResults
from testo_core.reporting.reporters.base import BaseReporter, ReportContext, ReporterResult

if TYPE_CHECKING:
    from rich.console import Console

    from testo_core.services.run_alerts import AlertChannel, AlertWhen


class _ChatAlertReporter(BaseReporter):
    channel: AlertChannel

    @property
    def reporter_type(self) -> str:
        return self.channel

    def publish(
        self,
        *,
        results: CollectedResults,
        context: ReportContext,
        console: Console | None = None,
    ) -> ReporterResult:
        from testo_core.services import run_alerts

        name = self.channel.capitalize()
        url = (self._options.get("webhook") or "").strip() or run_alerts.webhook_from_env(
            self.channel
        )
        if not url:
            env = run_alerts.WEBHOOK_ENV[self.channel]
            return ReporterResult(ok=False, message=f"{name}: set {env} or the webhook option.")
        when = (self._options.get("when") or "failure").strip().lower()
        if when not in run_alerts.WHEN_CHOICES:
            return ReporterResult(
                ok=False,
                message=f"{name}: when must be one of {', '.join(run_alerts.WHEN_CHOICES)}.",
            )
        if not context.run_id:
            return ReporterResult(ok=False, message=f"{name}: needs a recorded run (persist).")

        alert = run_alerts.load_alert(run_id=context.run_id)
        if alert is None:
            return ReporterResult(ok=False, message=f"{name}: run {context.run_id} not found.")
        if not run_alerts.should_send(alert, cast("AlertWhen", when)):
            return ReporterResult(ok=True, message=f"{name}: nothing to report (when: {when}).")

        payload = run_alerts.build_payload(
            self.channel,
            alert,
            title=(self._options.get("title") or "").strip() or None,
            run_url=(self._options.get("report_url") or "").strip() or None,
        )
        try:
            run_alerts.post(url, payload)
        except run_alerts.AlertError as exc:
            return ReporterResult(ok=False, message=f"{name}: {exc}")
        return ReporterResult(ok=True, message=f"{name} alert sent.")


class SlackReporter(_ChatAlertReporter):
    channel = "slack"


class TeamsReporter(_ChatAlertReporter):
    channel = "teams"
