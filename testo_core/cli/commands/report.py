"""``testo report`` — unified Allure reports and raw framework-native reports.

Default (no subcommand): generate / serve / export from Allure results.

``native``: open or list BehaveX HTML, pytest junit/html heuristics, etc.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import typer

from testo_core.engine.exit_codes import EngineExitCode

logger = logging.getLogger(__name__)

report_app = typer.Typer(
    name="report",
    help=(
        "Build unified Allure reports from the latest cycle, or access raw, framework-specific "
        "reports (e.g. BehaveX HTML) from the latest run."
    ),
    invoke_without_command=True,
    no_args_is_help=False,
)


@report_app.callback(invoke_without_command=True)
def report_callback(
    ctx: typer.Context,
    artifacts_root: Path = typer.Option(
        Path("artifacts"),
        "--artifacts",
        "-a",
        help="Artifacts root that holds per-cycle and per-stage outputs.",
    ),
    cycle: str | None = typer.Option(
        None,
        "--cycle",
        help="Restrict to one cycle's artifacts (YAML key under cycles:; legacy plans:).",
    ),
    plan: str | None = typer.Option(
        None,
        "--plan",
        "-p",
        help="Deprecated alias for --cycle.",
        hidden=True,
    ),
    generate_only: bool = typer.Option(
        False,
        "--generate-only",
        help="Write HTML to --out only; do not start the local HTTP dashboard (Allure path only).",
    ),
    host: str = typer.Option(
        "127.0.0.1",
        "--host",
        help="Host for the Allure dashboard (after allure generate).",
    ),
    port: int = typer.Option(
        8080,
        "--port",
        help="Port for the Allure dashboard; if busy, a free port is used automatically. Use 0 to always pick a free port.",
    ),
    out: Path = typer.Option(
        Path("artifacts/report"),
        "--out",
        "-o",
        help="Where to write the generated HTML report (Allure path only).",
    ),
    fmt: str = typer.Option(
        "html",
        "--format",
        "-f",
        help="Output format: html (default), json, or junit (Allure path only).",
    ),
    summary_out: Path | None = typer.Option(
        None,
        "--summary-out",
        help="When --format=json|junit, file path to write the machine-readable summary to.",
    ),
    no_history: bool = typer.Option(
        False,
        "--no-history",
        help="Do not inject Allure history/ from a prior DB-archived run before ``allure generate``.",
    ),
) -> None:
    """Build a unified Allure report from the latest (or selected) cycle, then open it locally."""
    resolved_cycle = cycle if cycle is not None else plan
    ctx.obj = {"artifacts_root": artifacts_root, "resolved_cycle": resolved_cycle}

    if ctx.invoked_subcommand is not None:
        return

    from testo_core.cli.ui.console import default_console
    from testo_core.reporting.entry import dispatch_report

    console = default_console()
    exit_code = dispatch_report(
        console=console,
        artifacts_root=artifacts_root,
        plan_name=resolved_cycle,
        generate_only=generate_only,
        port=port,
        host=host,
        out_dir=out,
        fmt=fmt,
        summary_out=summary_out,
        inject_history=not no_history,
    )
    raise typer.Exit(code=int(exit_code))


@report_app.command(
    "native",
    help="Open or list raw, framework-specific reports (e.g. BehaveX report.html) from the latest run.",
)
def report_native(
    ctx: typer.Context,
    routine_name: str | None = typer.Argument(
        None,
        metavar="[ROUTINE]",
        help="Stage (routine) directory name; omit to list native reports for the resolved cycle.",
    ),
    no_open: bool = typer.Option(
        False,
        "--no-open",
        help="Print paths only; do not open the default browser (mirrors Allure --generate-only style).",
    ),
) -> None:
    """List or open native HTML/XML under ``artifacts/<cycle>/<stage>/``.

    With no routine argument, prints a summary table then opens each discoverable HTML report
    in the browser (same idea as ``testo report`` for Allure). Use ``--no-open`` to list only.
    """
    from rich.table import Table

    from testo_core.cli.ui.console import default_console
    from testo_core.reporting.native_reports import (
        _infer_equipment,
        find_stage_dir,
        list_native_rows,
        load_stage_equipment,
        native_row_for_stage,
        open_native_uri,
        resolve_cycle_dir,
    )
    from testo_core.reporting.paths import relpath_for_display

    obj: dict[str, Any] = ctx.obj or {}
    artifacts_root = obj.get("artifacts_root") or Path("artifacts")
    resolved_cycle = obj.get("resolved_cycle")

    console = default_console()
    console.print(
        "[bold magenta]────────────────────────── Raw Equipment Specs ──────────────────────────[/]"
    )

    cycle_dir = resolve_cycle_dir(artifacts_root=artifacts_root, cycle=resolved_cycle)
    if cycle_dir is None:
        label = resolved_cycle or "(latest)"
        console.print(
            f"[fail]No cycle artifacts found for[/] {label} under {relpath_for_display(Path(artifacts_root))}"
        )
        raise typer.Exit(code=int(EngineExitCode.INVALID_INPUT))

    if routine_name is None or not str(routine_name).strip():
        rows = list_native_rows(cycle_dir=cycle_dir)
        if not rows:
            console.print(
                "[warn]No raw data found for this routine[/] — no stage directories under the cycle."
            )
            raise typer.Exit(code=0)

        table = Table(title="Native reports", show_lines=False, title_justify="left")
        table.add_column("Routine", style="title")
        table.add_column("Equipment", style="framework")
        table.add_column("Open", style="muted", overflow="fold", no_wrap=False)
        table.add_column("Notes")
        for r in rows:
            open_cell = relpath_for_display(r.open_path) if r.open_path else "—"
            notes = r.notes or ("ready" if r.open_path else "—")
            table.add_row(r.routine, r.equipment, open_cell, notes)
        console.print(table)
        for r in rows:
            if r.open_path is not None:
                uri = r.open_path.expanduser().resolve().as_uri()
                console.print(f"[dim]{r.routine} →[/] [link={uri}]{r.open_path.resolve()}[/]")
        console.print(f"[muted]cycle:[/] {relpath_for_display(cycle_dir)}")
        if not no_open:
            html_targets = [r for r in rows if r.open_path is not None and r.open_kind == "html"]
            any_failed = False
            for r in html_targets:
                target = r.open_path
                assert target is not None  # filtered above
                if open_native_uri(target):
                    console.print(
                        f"[ok]Opened[/] [html] {relpath_for_display(target)} [muted]({r.routine})[/]"
                    )
                else:
                    any_failed = True
                    console.print(
                        f"[fail]Could not open browser for[/] {target.resolve()} [muted]({r.routine})[/]"
                    )
            if any_failed:
                raise typer.Exit(code=int(EngineExitCode.INFRA_FAILURE))
        raise typer.Exit(code=0)

    routine = str(routine_name).strip()
    stage_dir = find_stage_dir(cycle_dir, routine)
    if stage_dir is None:
        console.print(
            f"[fail]Unknown routine[/] {routine!r} under {relpath_for_display(cycle_dir)}"
        )
        raise typer.Exit(code=int(EngineExitCode.INVALID_INPUT))

    eq_map = load_stage_equipment(cycle_dir)
    equipment = _infer_equipment(stage_dir, routine, eq_map)
    row = native_row_for_stage(stage_dir, equipment)

    if row.open_path is None:
        console.print("[warn]No raw data found for this routine[/]")
        if row.notes:
            console.print(f"[muted]{row.notes}[/]")
        raise typer.Exit(code=0)

    uri = row.open_path.expanduser().resolve().as_uri()
    console.print(f"[dim]path:[/] [link={uri}]{row.open_path.resolve()}[/]")
    if no_open:
        raise typer.Exit(code=0)

    if open_native_uri(row.open_path):
        console.print(f"[ok]Opened[/] [{row.open_kind}] {relpath_for_display(row.open_path)}")
        raise typer.Exit(code=0)

    console.print(
        f"[fail]Could not open the default browser for[/] {relpath_for_display(row.open_path)}"
    )
    raise typer.Exit(code=int(EngineExitCode.INFRA_FAILURE))


@report_app.command("list", help="List archived cycle reports stored in the database.")
def report_list_archived(
    limit: int = typer.Option(30, "--limit", "-n", help="Maximum number of rows to show."),
) -> None:
    from rich.table import Table

    from testo_core.cli.ui.console import default_console
    from testo_core.repository.db import get_report_archive_repository

    console = default_console()
    try:
        rows = get_report_archive_repository().list_recent(limit=limit)
    except Exception as exc:
        # Broad on purpose: any DB/driver error maps to exit 3 with its message.
        logger.debug("listing archived reports failed", exc_info=True)
        console.print(f"[fail]could not list reports:[/] {exc}")
        raise typer.Exit(code=int(EngineExitCode.INFRA_FAILURE)) from exc

    if not rows:
        console.print("[muted]No archived reports found.[/]")
        raise typer.Exit(code=0)

    table = Table(title="Archived reports", title_justify="left")
    table.add_column("id", style="bold", overflow="fold", min_width=36, no_wrap=True)
    table.add_column("cycle", style="title")
    table.add_column("created", style="muted")
    table.add_column("exit", justify="right")
    table.add_column("tests", justify="right")
    table.add_column("pass", justify="right")
    table.add_column("fail", justify="right")
    for r in rows:
        table.add_row(
            str(r.id),
            r.cycle_name,
            str(r.created_at),
            str(r.exit_code),
            "—" if r.total_tests is None else str(r.total_tests),
            "—" if r.passed is None else str(r.passed),
            "—" if r.failed is None else str(r.failed),
        )
    console.print(table)
    raise typer.Exit(code=0)


@report_app.command("open", help="Re-open an archived report from the database (Allure path).")
def report_open_archived(
    report_id: str = typer.Option(
        ...,
        "--id",
        help="Report archive UUID (primary key; use ``testo report list`` id column—not headless RunRecord id).",
    ),
    generate_only: bool = typer.Option(
        False,
        "--generate-only",
        help="Write HTML to --out only; do not start the Allure HTTP dashboard.",
    ),
    host: str = typer.Option("127.0.0.1", "--host", help="Host for the Allure dashboard."),
    port: int = typer.Option(
        8080,
        "--port",
        help="Port for the Allure dashboard; if busy, a free port is used automatically. Use 0 to always pick a free port.",
    ),
    out: Path = typer.Option(
        Path("artifacts/report"),
        "--out",
        "-o",
        help="Where to write the generated HTML report.",
    ),
    fmt: str = typer.Option(
        "html",
        "--format",
        "-f",
        help="Output format: html (default), json, or junit.",
    ),
    summary_out: Path | None = typer.Option(
        None,
        "--summary-out",
        help="When --format=json|junit, output file path.",
    ),
) -> None:
    import tempfile
    import uuid

    from testo_core.cli.ui.console import default_console
    from testo_core.reporting.entry import dispatch_report
    from testo_core.repository.db import get_report_archive_repository
    from testo_core.services.report_archive import extract_archive_to_plan_dir

    console = default_console()
    try:
        rid = uuid.UUID(str(report_id).strip())
    except (ValueError, TypeError):
        console.print(f"[fail]invalid report id:[/] {report_id!r}")
        raise typer.Exit(code=int(EngineExitCode.INVALID_INPUT)) from None

    try:
        row = get_report_archive_repository().get(rid)
    except Exception as exc:
        # Broad on purpose: any DB/driver error maps to exit 3 with its message.
        logger.debug("loading archived report %s failed", rid, exc_info=True)
        console.print(f"[fail]could not load report:[/] {exc}")
        raise typer.Exit(code=int(EngineExitCode.INFRA_FAILURE)) from exc

    if row is None:
        console.print(f"[fail]no archived report with id[/] {rid}")
        raise typer.Exit(code=int(EngineExitCode.INVALID_INPUT))

    with tempfile.TemporaryDirectory(prefix="testo-report-") as td:
        root = Path(td)
        extract_archive_to_plan_dir(
            zip_bytes=row.artifact_bytes,
            dest_artifacts_root=root,
            plan_name=row.cycle_name,
        )
        exit_code = dispatch_report(
            console=console,
            artifacts_root=root,
            plan_name=row.cycle_name,
            generate_only=generate_only,
            port=port,
            host=host,
            out_dir=out,
            fmt=fmt,
            summary_out=summary_out,
            inject_history=False,
        )
    raise typer.Exit(code=int(exit_code))


@report_app.command(
    "pyramid", help="Render the unit/integration/e2e test pyramid for a completed run."
)
def report_pyramid(
    run_id: str = typer.Argument(
        ...,
        metavar="RUN_ID",
        help="Completed run id (same id shown in the dashboard/history views).",
    ),
    config: Path = typer.Option(
        None,
        "--config",
        "-c",
        help="Path to a testosterone.yaml file (defaults to discovery).",
    ),
) -> None:
    from testo_core.cli.ui.console import default_console
    from testo_core.config.errors import ConfigError
    from testo_core.config.loader import discover_and_load
    from testo_core.history.read_model import get_run
    from testo_core.reporting.pyramid_data import build_pyramid_model, run_needs_config_tiers
    from testo_core.reporting.pyramid_viz import classify_shape, render_pyramid_lines

    console = default_console()
    run = get_run(run_id=run_id)
    if run is None:
        console.print(f"[fail]no run found with id[/] {run_id!r}")
        raise typer.Exit(code=int(EngineExitCode.INVALID_INPUT))

    # Runs record each stage's tier. Only older records without one fall back
    # to the tiers in the current YAML.
    stages: tuple[Any, ...] = ()
    if run.cycle and run_needs_config_tiers(run):
        try:
            cfg = discover_and_load(config_path=config)
        except ConfigError as exc:
            console.print(f"[fail]config error:[/] {exc}")
            raise typer.Exit(code=int(EngineExitCode.INVALID_INPUT)) from exc
        plan = cfg.cycles.get(run.cycle)
        if plan is not None:
            stages = plan.stages

    model = build_pyramid_model(run, stages)
    shape, message = classify_shape(model)
    console.print(f"[title]Test Pyramid[/] — {run_id} ({run.cycle or 'unknown cycle'})")
    for line in render_pyramid_lines(model):
        console.print(line)
    console.print(
        f"unit={model.unit} integration={model.integration} e2e={model.e2e} "
        f"shape={shape.value} — {message}"
    )
    raise typer.Exit(code=0)


@report_app.command(
    "markdown",
    help="A run as Markdown (job summary or pull request comment): results, failures, changes.",
)
def report_markdown(
    cycle: str | None = typer.Option(None, "--cycle", help="Latest run of this cycle."),
    run_id: str | None = typer.Option(None, "--run-id", help="A specific run (run-history id)."),
    out: Path | None = typer.Option(
        None, "--out", "-o", help="Write to this file instead of stdout."
    ),
    run_url: str | None = typer.Option(
        None, "--run-url", help="Link added to the footer, e.g. the CI run that produced it."
    ),
) -> None:
    from testo_core.services.run_summary_markdown import load_run_summary, render_markdown

    summary = load_run_summary(cycle=cycle.strip() if cycle else None, run_id=run_id)
    if summary is None:
        typer.echo("no recorded run found", err=True)
        raise typer.Exit(code=int(EngineExitCode.INVALID_INPUT))
    text = render_markdown(summary, run_url=run_url)
    if out is None:
        typer.echo(text, nl=False)
    else:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
    raise typer.Exit(code=0)
