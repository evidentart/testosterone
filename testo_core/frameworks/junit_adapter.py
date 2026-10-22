"""``junit`` adapter: record results that some other step already produced.

A ``junit`` stage runs no process. The executor reads the stage's
``junit_xml`` globs (written earlier by any runner, in any language), converts
them into Allure result files like it does after a ``command`` stage, and
derives the stage's returncode from the results: 1 when a case failed or broke,
or when nothing matched; 0 otherwise. ``testo ingest`` builds a one-stage cycle
with this equipment, so ingested runs go through the same engine, history,
reporters and Compare as runs Testosterone started itself.
"""

from __future__ import annotations

from pathlib import Path

from testo_core.frameworks.base import NativeReport


class JunitAdapter:
    name: str = "junit"
    # Read by the executor: import ``junit_xml`` instead of launching ``build_argv``.
    runs_process: bool = False

    def results_subdir(self) -> str:
        return "junit"

    def build_argv(
        self,
        *,
        target_repo: Path,
        results_dir: Path,
        stage_args: tuple[str, ...],
        workers: int,
    ) -> list[str]:
        del target_repo, results_dir, stage_args, workers
        return []

    def native_report(self, stage_dir: Path) -> NativeReport | None:
        del stage_dir
        return None
