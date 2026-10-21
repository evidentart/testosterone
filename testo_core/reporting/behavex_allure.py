"""Turn a BehaveX run's ``report.json`` into Allure ``*-result.json`` files.

BehaveX writes its HTML report only when no ``--formatter`` is passed
(``behavex.utils.generate_reports``), so the BehaveX adapter runs it plain and
the executor calls :func:`export_behavex_allure_results` after the stage. That
gives every run both reports:

    <stage>/behave_reports/report.html       BehaveX's own report (native report)
    <stage>/behave_reports/report.json       what the export below reads
    <stage>/allure-results/behavex/*.json    Allure results for summaries and reporters

The conversion is BehaveX's own ``AllureBehaveXFormatter``, the same code that
runs for ``--formatter``, so the results match a formatter run file for file.
The formatter expects scenario logs and evidence inside its output directory
(``--formatter`` points BehaveX's ``LOGS`` there) and links them relatively, so
they are copied in first.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any


def export_behavex_allure_results(report_dir: Path, results_dir: Path) -> int | None:
    """Write Allure results for the BehaveX run in ``report_dir`` into ``results_dir``.

    Returns the number of scenarios exported, or ``None`` when there is nothing
    to do: no ``report.json`` (BehaveX never got that far), or ``results_dir``
    already holds results (the stage passed its own ``--formatter``).
    Raises when the report can't be read or converted; the executor records that
    on the stage without changing its exit code.
    """
    report_json = report_dir / "report.json"
    if not report_json.is_file():
        return None
    if any(results_dir.glob("*-result.json")):
        return None

    payload: dict[str, Any] = json.loads(report_json.read_text(encoding="utf-8"))
    results_dir.mkdir(parents=True, exist_ok=True)
    logs_dir = report_dir / "outputs" / "logs"
    if logs_dir.is_dir():
        shutil.copytree(logs_dir, results_dir, dirs_exist_ok=True)

    # The formatter reads its output dir from BehaveX's process-wide ConfigRun
    # (lowercase keys), not from arguments; swap it in and restore it after.
    from behavex.conf_mgr import ConfigRun
    from behavex.outputs.formatters.allure_behavex_formatter import AllureBehaveXFormatter

    config = ConfigRun()
    saved_environ = dict(config.environ)
    try:
        config.environ["output"] = str(report_dir.resolve())
        config.environ["logs"] = str(results_dir.resolve())
        AllureBehaveXFormatter().launch_json_formatter(payload)
    finally:
        config.environ.clear()
        config.environ.update(saved_environ)

    return sum(len(feature.get("scenarios", [])) for feature in payload.get("features", []))
