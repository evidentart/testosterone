"""Example Testosterone plugin.

- ``UnittestAdapter`` (``equipment: unittest``) runs the standard library's
  unittest and writes one Allure result file per test, so the run shows up in
  ``testo summary``, ``testo flaky`` and the UI like any built-in runner.
- ``JsonSummaryReporter`` (``reporters: [{type: json-summary, out_dir: ...}]``)
  writes the cycle's pass/fail counts to ``<out_dir>/summary.json`` after
  every run (``out_dir`` is resolved against the config file's folder).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from testo_core.frameworks.base import NativeReport
from testo_core.reporting.allure_results import parse_collected_results
from testo_core.reporting.reporters.base import BaseReporter, ReporterResult


class UnittestAdapter:
    name = "unittest"

    def results_subdir(self) -> str:
        return "unittest"

    def build_argv(
        self,
        *,
        target_repo: Path,
        results_dir: Path,
        stage_args: tuple[str, ...],
        workers: int,
    ) -> list[str]:
        # The process runs with target_repo as its working directory.
        del target_repo, workers
        return [
            sys.executable,
            "-m",
            "testo_example_plugin.runner",
            str(results_dir),
            *stage_args,
        ]

    def native_report(self, stage_dir: Path) -> NativeReport | None:
        del stage_dir
        return None


class JsonSummaryReporter(BaseReporter):
    @property
    def reporter_type(self) -> str:
        return "json-summary"

    def publish(self, *, results, context, console=None) -> ReporterResult:  # noqa: ANN001
        totals = parse_collected_results(results)
        out = Path(self._options.get("out_dir", "reports")) / "summary.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "cycle": context.plan_name,
            "run_id": context.run_id,
            "total": totals.total,
            "passed": totals.passed,
            "failed": totals.failed,
            "skipped": totals.skipped,
        }
        out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        return ReporterResult(ok=True, message=f"json-summary: wrote {out}", artifacts=(out,))
