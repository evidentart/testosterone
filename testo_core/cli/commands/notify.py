"""``testo notify`` — send a recorded run to Slack and/or Microsoft Teams."""

from __future__ import annotations

from typing import cast

import typer

from testo_core.engine.exit_codes import EngineExitCode


def notify(
    to: list[str] = typer.Option(
        ...,
        "--to",
        help="slack or teams; repeat for both. URLs come from $TESTO_SLACK_WEBHOOK_URL "
        "and $TESTO_TEAMS_WEBHOOK_URL.",
    ),
    cycle: str | None = typer.Option(None, "--cycle", help="Latest run of this cycle."),
    run_id: str | None = typer.Option(None, "--run-id", help="A specific run (run-history id)."),
    when: str = typer.Option(
        "failure",
        "--when",
        help="failure: red run or newly flaky test. change: differs from the previous run. "
        "always: every run.",
    ),
    title: str | None = typer.Option(None, "--title", help="Name in the message (default: cycle)."),
    run_url: str | None = typer.Option(
        None, "--run-url", help="'View run' link, e.g. the CI run that produced it."
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Print the JSON payloads instead of sending them."
    ),
) -> None:
    """Send the run (failing tests, regressions, newly flaky tests) to chat webhooks."""
    import json

    from testo_core.services import run_alerts

    channels = [c.strip().lower() for c in to]
    bad = [c for c in channels if c not in run_alerts.CHANNELS]
    if bad or when not in run_alerts.WHEN_CHOICES:
        typer.echo(
            f"--to takes {' / '.join(run_alerts.CHANNELS)} and --when takes "
            f"{' / '.join(run_alerts.WHEN_CHOICES)}",
            err=True,
        )
        raise typer.Exit(code=int(EngineExitCode.INVALID_INPUT))
    targets = cast("list[run_alerts.AlertChannel]", list(dict.fromkeys(channels)))

    urls = {c: run_alerts.webhook_from_env(c) for c in targets}
    missing = [run_alerts.WEBHOOK_ENV[c] for c, url in urls.items() if not url]
    if missing and not dry_run:
        typer.echo(f"not set: {', '.join(missing)}", err=True)
        raise typer.Exit(code=int(EngineExitCode.INVALID_INPUT))

    alert = run_alerts.load_alert(cycle=cycle.strip() if cycle else None, run_id=run_id)
    if alert is None:
        typer.echo("no recorded run found", err=True)
        raise typer.Exit(code=int(EngineExitCode.INVALID_INPUT))
    if not run_alerts.should_send(alert, cast("run_alerts.AlertWhen", when)):
        typer.echo(f"nothing to report (--when {when})", err=True)
        raise typer.Exit(code=0)

    failed = False
    for channel in targets:
        payload = run_alerts.build_payload(channel, alert, title=title, run_url=run_url)
        if dry_run:
            typer.echo(json.dumps({channel: payload}, indent=2, ensure_ascii=False))
            continue
        try:
            run_alerts.post(urls[channel], payload)
        except run_alerts.AlertError as exc:
            typer.echo(f"{channel}: {exc}", err=True)
            failed = True
        else:
            typer.echo(f"{channel}: sent", err=True)
    raise typer.Exit(code=int(EngineExitCode.INFRA_FAILURE) if failed else 0)
