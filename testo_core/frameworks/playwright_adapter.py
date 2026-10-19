"""Playwright Test adapter — ``npx playwright test`` with results Testosterone can read.

The stage's ``args`` are passed to ``playwright test`` (test files, ``--project``,
``--grep``...). The adapter adds what a ``command`` stage would need by hand:

- ``--reporter=list,junit,html`` (unless ``args`` set ``--reporter``). JUnit goes to
  ``<target_repo>/test-results/testo-junit.xml``, which the executor imports as
  Allure results (``default_junit_xml``); the HTML report goes to the stage's
  artifacts dir and is copied into the run's history as its native report.
- ``--workers=N`` from the stage's ``workers`` (unless ``args`` set it).

Playwright itself must be installed in the target project (``npm i -D @playwright/test``).
"""

from __future__ import annotations

from pathlib import Path

from testo_core.frameworks.base import NativeReport

JUNIT_RELPATH = "test-results/testo-junit.xml"
HTML_DIRNAME = "playwright-report"


def _has_flag(args: tuple[str, ...], *flags: str) -> bool:
    return any(a in flags or a.startswith(tuple(f"{f}=" for f in flags)) for a in args)


class PlaywrightAdapter:
    name: str = "playwright"
    # Imported after the stage when its own ``junit_xml`` is not set.
    default_junit_xml: tuple[str, ...] = (JUNIT_RELPATH,)

    def results_subdir(self) -> str:
        return "playwright"

    def build_argv(
        self,
        *,
        target_repo: Path,
        results_dir: Path,
        stage_args: tuple[str, ...],
        workers: int,
    ) -> list[str]:
        del target_repo, results_dir
        argv = ["npx", "playwright", "test", *stage_args]
        if not _has_flag(stage_args, "--reporter"):
            argv.append("--reporter=list,junit,html")
        if workers > 0 and not _has_flag(stage_args, "--workers", "-j"):
            argv.append(f"--workers={workers}")
        return argv

    def stage_env(self, *, target_repo: Path, results_dir: Path) -> dict[str, str]:
        # results_dir is <stage>/allure-results/playwright
        stage_dir = results_dir.parent.parent
        return {
            "PLAYWRIGHT_JUNIT_OUTPUT_FILE": str(target_repo.expanduser().resolve() / JUNIT_RELPATH),
            "PLAYWRIGHT_HTML_OUTPUT_DIR": str(stage_dir / HTML_DIRNAME),
            "PLAYWRIGHT_HTML_OPEN": "never",
        }

    def native_report(self, stage_dir: Path) -> NativeReport | None:
        root = stage_dir / HTML_DIRNAME
        if not (root / "index.html").is_file():
            return None
        return NativeReport(root_dir=root, entry_relpath="index.html")
