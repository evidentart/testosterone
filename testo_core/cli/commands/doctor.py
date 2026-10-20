"""``testo doctor`` — quick health checks for local Testosterone setups."""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

import typer

from testo_core.engine.exit_codes import EngineExitCode

logger = logging.getLogger(__name__)


def _check_node() -> tuple[str, str]:
    node = shutil.which("node")
    if not node:
        return "[warn]WARN[/]", "Node.js not on PATH (required for Allure Report 3)"
    try:
        proc = subprocess.run(  # noqa: S603
            [node, "--version"],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        ver = (proc.stdout or proc.stderr or "").strip() or "unknown"
        return "[ok]PASS[/]", f"{node} ({ver})"
    except (OSError, subprocess.TimeoutExpired) as exc:
        return "[warn]WARN[/]", f"node found but version check failed: {exc}"


def _check_allure3() -> tuple[str, str]:
    from testo_core.reporting.allure_cli import (
        AllureCLINotFoundError,
        find_repo_root,
        resolve_allure_command,
    )

    try:
        cmd = resolve_allure_command(repo_root=find_repo_root())
        return "[ok]PASS[/]", " ".join(cmd.argv)
    except (AllureCLINotFoundError, OSError) as exc:
        return "[warn]WARN[/]", str(exc)


def doctor(
    config: Path | None = typer.Option(
        None,
        "--config",
        "-c",
        help="Path to testosterone.yaml (defaults to discovery).",
    ),
) -> None:
    """Validate config load, optional DB reachability, and common CLIs on PATH."""
    from rich.table import Table

    from testo_core.cli.ui.console import default_console
    from testo_core.config.errors import ConfigError
    from testo_core.config.loader import discover_and_load

    console = default_console()
    table = Table(title="Doctor", show_lines=False)
    table.add_column("Check", style="title")
    table.add_column("Status", style="bold")
    table.add_column("Detail", overflow="fold")

    hard_fail = False
    db_url: str | None = None
    cfg = None

    try:
        cfg = discover_and_load(config_path=config)
        table.add_row("Config load", "[ok]PASS[/]", f"cycles={len(cfg.cycles)}")
    except ConfigError as exc:
        hard_fail = True
        table.add_row("Config load", "[fail]FAIL[/]", str(exc))

    if cfg is not None:
        used_fw: set[str] = set()
        for plan in cfg.cycles.values():
            for st in plan.stages:
                used_fw.add(str(st.framework))
        exe_map = {
            "pytest": "pytest",
            "behave": "behave",
            "behavex": "behavex",
            "playwright": "npx",
        }
        for fw in sorted(used_fw):
            exe = exe_map.get(fw)
            if not exe:
                continue
            if shutil.which(exe):
                table.add_row(f"CLI `{exe}`", "[ok]PASS[/]", "on PATH")
            else:
                hard_fail = True
                table.add_row(f"CLI `{exe}`", "[fail]FAIL[/]", "not found on PATH")

    node_status, node_detail = _check_node()
    table.add_row("Node.js", node_status, node_detail)

    allure_status, allure_detail = _check_allure3()
    table.add_row("Allure Report 3 CLI", allure_status, allure_detail)

    docker_path = shutil.which("docker")
    if docker_path:
        table.add_row("Docker CLI", "[ok]PASS[/]", docker_path)
    else:
        table.add_row(
            "Docker CLI", "[warn]WARN[/]", "`docker` not on PATH (optional for some workflows)"
        )

    legacy_java = shutil.which("allure")
    if legacy_java and allure_status.startswith("[warn]"):
        table.add_row(
            "Legacy Allure 2 CLI",
            "[dim]INFO[/]",
            f"Java `allure` at {legacy_java} — Testo uses Allure Report 3 (Node.js) instead",
        )

    if cfg is not None:
        import os

        from testo_core.config.database_section import database_url_from_discovered_config

        anchor = cfg.source_path.parent.expanduser().resolve() if cfg.source_path else Path.cwd()
        db_url = (
            os.environ.get("DATABASE_URL") or ""
        ).strip() or database_url_from_discovered_config(cwd=anchor)
        db_url = db_url or None

    if db_url:
        try:
            from urllib.parse import urlparse

            from sqlalchemy import create_engine, text
        except ImportError:
            table.add_row("Database", "[dim]SKIP[/]", "install testo-core[db] for SQLAlchemy probe")
        else:
            try:
                dialect = urlparse(db_url).scheme.lower().split("+", 1)[0]
                eng_kwargs: dict[str, object] = {}
                if dialect == "sqlite":
                    eng_kwargs["connect_args"] = {"check_same_thread": False}
                else:
                    eng_kwargs["pool_pre_ping"] = True
                eng = create_engine(db_url, **eng_kwargs)
                with eng.connect() as conn:
                    conn.execute(text("SELECT 1"))
                table.add_row("Database", "[ok]PASS[/]", "connection probe succeeded")
            except Exception as exc:
                # Broad on purpose: any driver/URL/connection error is reported as a FAIL row.
                logger.debug("database probe failed", exc_info=True)
                hard_fail = True
                table.add_row("Database", "[fail]FAIL[/]", str(exc))
    else:
        table.add_row("Database", "[dim]SKIP[/]", "no database.url / DATABASE_URL")

    console.print(table)
    if hard_fail:
        console.print("[fail]One or more required checks failed.[/]")
        raise typer.Exit(code=int(EngineExitCode.INVALID_INPUT))
    console.print("[ok]Doctor checks passed (optional warnings may remain).[/]")
