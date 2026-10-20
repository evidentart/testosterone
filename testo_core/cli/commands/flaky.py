"""``testo flaky`` — tests whose outcome keeps flipping across a cycle's recent runs."""

from __future__ import annotations

import json
from dataclasses import asdict

import typer

from testo_core.engine.exit_codes import EngineExitCode

_MARK = {"passed": "[ok]✓[/]", "failed": "[fail]✗[/]", "broken": "[fail]✗[/]"}


def flaky(
    cycle: str = typer.Option(..., "--cycle", help="Cycle whose run history to analyze."),
    window: int = typer.Option(
        20, "--window", min=2, help="How many of the cycle's most recent runs to look at."
    ),
    as_json: bool = typer.Option(False, "--json", help="Print the report as JSON."),
    fail_on_flaky: bool = typer.Option(
        False, "--fail-on-flaky", help="Exit 1 when any flaky test is found (for CI gates)."
    ),
) -> None:
    """List tests that both passed and failed, flipping at least twice, in the last runs."""
    from rich.table import Table

    from testo_core.cli.ui.console import default_console
    from testo_core.services.flaky_service import find_flaky_tests

    report = find_flaky_tests(cycle=cycle.strip(), window=window)
    exit_code = int(EngineExitCode.DOMAIN_FAILURE) if (fail_on_flaky and report.flaky) else 0

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
        console.print("[ok]No flaky tests.[/]")
        raise typer.Exit(code=exit_code)

    table = Table(title=f"Flaky tests ({len(report.flaky)})", title_justify="left")
    table.add_column("Test")
    table.add_column("Group", style="muted")
    table.add_column("Pass / fail", justify="right")
    table.add_column("Flips", justify="right")
    table.add_column("History (oldest → newest)")
    for t in report.flaky:
        history = "".join(_MARK.get(s, "[muted]·[/]") for s in t.history)
        table.add_row(t.name, t.group, f"{t.passed} / {t.failed}", str(t.flips), history)
    console.print(table)
    raise typer.Exit(code=exit_code)
