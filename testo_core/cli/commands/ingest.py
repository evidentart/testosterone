"""``testo ingest`` — record JUnit XML that another step already wrote, as a run of a cycle.

The low-effort way in: keep your CI as it is, add one step after the tests,
and every run lands in Testosterone's history (Compare, trends, ``testo flaky``,
reporters, PR comment). Works for any runner that writes JUnit XML: pytest,
Jest, Vitest, Playwright, ``go test``, JUnit5, Maestro, ...

With ``--server`` the files go to a shared Testosterone server instead, so
every CI job of a team records into one history.
"""

from __future__ import annotations

from pathlib import Path

import typer


def ingest(
    reports: list[str] = typer.Argument(
        ...,
        help=(
            "JUnit XML files or glob patterns (quote globs: 'reports/**/*.xml'), "
            "relative to --repo or inside it."
        ),
    ),
    cycle: str = typer.Option(
        ...,
        "--cycle",
        help="Cycle to record the run under. Use the same name every time to build its history.",
    ),
    stage: str = typer.Option("junit", "--stage", help="Stage name the tests are grouped under."),
    tier: str = typer.Option(
        "unit", "--tier", help="Test-pyramid tier of these tests: unit, integration or e2e."
    ),
    repo: Path = typer.Option(
        Path("."),
        "--repo",
        file_okay=False,
        help="Directory the report paths are relative to (default: the current directory).",
    ),
    config: Path = typer.Option(
        None,
        "--config",
        "-c",
        dir_okay=False,
        help="testosterone.yaml for reporters and the database (optional; discovered if present).",
    ),
    ci: bool = typer.Option(
        False,
        "--ci",
        help="Emit NDJSON events on stdout instead of Rich panels (machine-readable).",
    ),
    no_persist: bool = typer.Option(
        False,
        "--no-persist",
        help="Skip all persistence (only useful to check that the reports parse).",
    ),
    server: str = typer.Option(
        None,
        "--server",
        envvar="TESTO_SERVER_URL",
        help="Upload to this Testosterone server (team history) instead of recording locally.",
    ),
    token: str = typer.Option(
        None,
        "--token",
        envvar="TESTO_API_TOKEN",
        help="The server's API token (default: $TESTO_API_TOKEN).",
    ),
) -> None:
    """Record JUnit XML results from any runner as a run of a cycle."""
    from testo_core.cli.runner import execute_ingest_command
    from testo_core.cli.ui.console import default_console, make_console

    console = make_console(plain=True) if ci else default_console()
    exit_code = execute_ingest_command(
        console=console,
        reports=reports,
        cycle=cycle,
        stage=stage,
        tier=tier,
        repo=repo,
        config_path=config,
        ci=ci,
        persist=not no_persist,
        server=server,
        token=token,
    )
    raise typer.Exit(code=int(exit_code))
