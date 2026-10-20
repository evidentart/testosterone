"""``testo plugins`` — list the frameworks and reporters this install can use.

Built-ins come first, then packages that registered ``testo.frameworks`` or
``testo.reporters`` entry points (:mod:`testo_core.plugins`). ``--check``
imports every plugin and exits 1 if one fails, which is the quick test a
plugin author wants after ``pip install -e .``.
"""

from __future__ import annotations

import json

import typer


def plugins_cmd(
    check: bool = typer.Option(
        False, "--check", help="Import every plugin and verify its interface; exit 1 on failure."
    ),
    as_json: bool = typer.Option(False, "--json", help="Print JSON instead of a table."),
) -> None:
    from rich.console import Console
    from rich.table import Table

    from testo_core import plugins
    from testo_core.config.schema import SUPPORTED_FRAMEWORKS, SUPPORTED_REPORTER_TYPES

    rows: list[dict[str, str | None]] = []
    for kind, names in (
        ("framework", SUPPORTED_FRAMEWORKS),
        ("reporter", SUPPORTED_REPORTER_TYPES),
    ):
        rows += [
            {"kind": kind, "name": n, "target": None, "package": "built in", "status": "ok"}
            for n in sorted(names)
        ]

    failed = 0
    for info in plugins.list_plugins():
        status: str | None = None
        if check:
            try:
                if info.kind == "framework":
                    plugins.load_framework(info.name)
                else:
                    plugins.load_reporter(info.name)
                status = "ok"
            except plugins.PluginError as exc:
                status = f"error: {exc}"
                failed += 1
        rows.append(
            {
                "kind": info.kind,
                "name": info.name,
                "target": info.target,
                "package": info.package,
                "status": status,
            }
        )

    if as_json:
        typer.echo(json.dumps(rows, indent=2))
    else:
        table = Table(title="Frameworks and reporters")
        for col in ("Kind", "Name", "From", "Entry point", *(["Status"] if check else [])):
            table.add_column(col)
        for r in rows:
            cells = [r["kind"] or "", r["name"] or "", r["package"] or "?", r["target"] or ""]
            if check:
                cells.append(r["status"] or "")
            table.add_row(*cells)
        Console().print(table)
        if not plugins.list_plugins():
            typer.echo(
                "No plugins installed. A package adds one with a 'testo.frameworks' or "
                "'testo.reporters' entry point; see the Command Reference."
            )
    if failed:
        raise typer.Exit(code=1)
