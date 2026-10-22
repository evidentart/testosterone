"""``testo flaky`` — tests whose outcome keeps flipping across a cycle's recent runs."""

from __future__ import annotations

import json
from dataclasses import asdict, replace
from pathlib import Path
from typing import TYPE_CHECKING

import typer

from testo_core.engine.exit_codes import EngineExitCode

if TYPE_CHECKING:
    from testo_core.config.schema import QuarantineRule

_MARK = {"passed": "[ok]✓[/]", "failed": "[fail]✗[/]", "broken": "[fail]✗[/]"}


def flaky(
    cycle: str = typer.Option(..., "--cycle", help="Cycle whose run history to analyze."),
    window: int = typer.Option(
        20, "--window", min=2, help="How many of the cycle's most recent runs to look at."
    ),
    new: bool = typer.Option(
        False, "--new", help="Only tests that the cycle's latest run made flaky."
    ),
    as_json: bool = typer.Option(False, "--json", help="Print the report as JSON."),
    fail_on_flaky: bool = typer.Option(
        False,
        "--fail-on-flaky",
        help="Exit 1 when any flaky test that isn't quarantined is found (for CI gates).",
    ),
    config: Path | None = typer.Option(
        None,
        "--config",
        help="testosterone.yaml whose 'quarantine:' rules mark tests (default: auto-discover).",
    ),
) -> None:
    """List tests that both passed and failed, flipping at least twice, in the last runs."""
    from rich.markup import escape
    from rich.table import Table

    from testo_core.cli.ui.console import default_console
    from testo_core.config.errors import ConfigError
    from testo_core.services.flaky_service import find_flaky_tests, newly_flaky_tests

    report = find_flaky_tests(cycle=cycle.strip(), window=window)
    if new:
        report = replace(report, flaky=newly_flaky_tests(cycle=report.cycle, window=window))
    try:
        rules = _quarantine_rules(report.cycle, config)
    except ConfigError as exc:
        default_console().print(f"[fail]config error:[/] {escape(str(exc))}")
        raise typer.Exit(code=int(EngineExitCode.INVALID_INPUT)) from exc
    if rules:
        from testo_core.engine.quarantine import matching_rule

        report = replace(
            report,
            flaky=tuple(
                replace(
                    t,
                    quarantined=matching_rule(rules, name=t.name, full_name=t.full_name)
                    is not None,
                )
                for t in report.flaky
            ),
        )
    open_flaky = [t for t in report.flaky if not t.quarantined]
    exit_code = int(EngineExitCode.DOMAIN_FAILURE) if (fail_on_flaky and open_flaky) else 0

    if as_json:
        typer.echo(json.dumps(asdict(report), indent=2))
        raise typer.Exit(code=exit_code)

    console = default_console()
    if report.runs_analyzed < 2:
        console.print(
            f"[warn]Need at least two recorded runs of cycle {report.cycle!r} with per-test "
            f"results; found {report.runs_analyzed}.[/]"
        )
        raise typer.Exit(code=int(EngineExitCode.INVALID_INPUT))

    console.print(
        f"[muted]{report.tests_analyzed} tests across the last {report.runs_analyzed} runs "
        f"of[/] [bold]{report.cycle}[/]"
    )
    if not report.flaky:
        console.print(f"[ok]No {'newly ' if new else ''}flaky tests.[/]")
        raise typer.Exit(code=exit_code)

    table = Table(title=f"Flaky tests ({len(report.flaky)})", title_justify="left")
    table.add_column("Test")
    table.add_column("Group", style="muted")
    table.add_column("Pass / fail", justify="right")
    table.add_column("Flips", justify="right")
    table.add_column("History (oldest → newest)")
    table.add_column("Quarantined")
    for t in report.flaky:
        history = "".join(_MARK.get(s, "[muted]·[/]") for s in t.history)
        table.add_row(
            escape(t.name),
            escape(t.group),
            f"{t.passed} / {t.failed}",
            str(t.flips),
            history,
            "[warn]yes[/]" if t.quarantined else "",
        )
    console.print(table)
    if open_flaky:
        console.print(
            "[muted]To stop these failing the build while they're fixed, add them to "
            f"cycle {report.cycle!r} in testosterone.yaml:[/]"
        )
        snippet = "\n".join(
            ["quarantine:"] + [f"  - test: {json.dumps(t.name)}" for t in open_flaky]
        )
        console.print(escape(snippet), highlight=False)
    raise typer.Exit(code=exit_code)


def _quarantine_rules(cycle: str, config: Path | None) -> tuple[QuarantineRule, ...]:
    """The cycle's quarantine rules; none when no config is found and none was given."""
    from testo_core.config.errors import ConfigDiscoveryError
    from testo_core.config.loader import discover_and_load

    try:
        cfg = discover_and_load(config_path=config)
    except ConfigDiscoveryError:
        if config is not None:
            raise
        return ()
    plan = cfg.cycles.get(cycle)
    return plan.quarantine if plan is not None else ()
