"""BehaveX adapter — parallel Behave with BehaveX's own HTML report.

No ``--formatter`` is added: BehaveX skips ``report.html`` whenever one is set.
The executor turns ``report.json`` into Allure results after the stage instead
(:mod:`testo_core.reporting.behavex_allure`).
"""

from __future__ import annotations

import tempfile
from collections.abc import Sequence
from pathlib import Path

from testo_core.frameworks.base import NativeReport


class BehaveXAdapter:
    name: str = "behavex"

    def results_subdir(self) -> str:
        return "behavex"

    def build_argv(
        self,
        *,
        target_repo: Path,
        results_dir: Path,
        stage_args: tuple[str, ...],
        workers: int,
    ) -> list[str]:
        del target_repo  # behavex picks up its own working dir
        # ``results_dir`` is ``<stage>/allure-results/<framework>/`` — native BehaveX output
        # must be a *sibling* of ``allure-results/``, not nested under it.
        behavex_output = results_dir.parent.parent / "behave_reports"
        behavex_output.mkdir(parents=True, exist_ok=True)
        results_dir.mkdir(parents=True, exist_ok=True)

        argv: list[str] = ["behavex", "-o", str(behavex_output.resolve())]
        argv.extend(_strip_output_folder_flags(stage_args))

        if not _contains(argv, "--parallel-processes"):
            argv.extend(["--parallel-processes", str(max(1, int(workers)))])
        if not _contains(argv, "--parallel-scheme"):
            argv.extend(["--parallel-scheme", "feature"])
        return argv

    def extra_env(self) -> dict[str, str]:
        # BehaveX points ``TEMP`` at ``<output>/temp``; Python's ``tempfile`` then puts the
        # multiprocessing manager's socket there, which overflows the ~108-char AF_UNIX path
        # limit for most checkouts. ``TMPDIR`` wins over ``TEMP``, so pin it to the system temp.
        return {"TMPDIR": tempfile.gettempdir()}

    def native_report(self, stage_dir: Path) -> NativeReport | None:
        root_dir = stage_dir / "behave_reports"
        if not (root_dir / "report.html").is_file():
            return None
        return NativeReport(root_dir=root_dir, entry_relpath="report.html")


def _strip_output_folder_flags(args: Sequence[str]) -> list[str]:
    out: list[str] = []
    i = 0
    items = list(args)
    while i < len(items):
        if items[i] in ("-o", "--output-folder"):
            i += 2
            continue
        out.append(items[i])
        i += 1
    return out


def _contains(argv: list[str], flag: str) -> bool:
    return any(arg == flag or arg.startswith(f"{flag}=") for arg in argv)
