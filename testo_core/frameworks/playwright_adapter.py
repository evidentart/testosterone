"""Playwright Test adapter — ``npx playwright test`` with results Testosterone can read.

The stage's ``args`` are passed to ``playwright test`` (test files, ``--project``,
``--grep``...). The adapter adds what a ``command`` stage would need by hand:

- ``--reporter=list,json,html`` (unless ``args`` set ``--reporter``). The JSON
  report goes to ``<target_repo>/test-results/testo-results.json``, which the
  executor imports as Allure results (``default_junit_xml``) with every retry,
  flaky tests and attachments (traces, screenshots); see
  :mod:`testo_core.reporting.playwright_import`. A stage that picks its own
  reporters can use ``junit`` instead: its file is imported when no JSON report
  was written. The HTML report goes to the stage's artifacts dir and is copied
  into the run's history as its native report.
- ``--workers=N`` from the stage's ``workers`` (unless ``args`` set it).

Playwright itself must be installed in the target project (``npm i -D @playwright/test``).
"""

from __future__ import annotations

from pathlib import Path

from testo_core.frameworks.base import NativeReport

JSON_RELPATH = "test-results/testo-results.json"
JUNIT_RELPATH = "test-results/testo-junit.xml"
HTML_DIRNAME = "playwright-report"


def _has_flag(args: tuple[str, ...], *flags: str) -> bool:
    return any(a in flags or a.startswith(tuple(f"{f}=" for f in flags)) for a in args)


class PlaywrightAdapter:
    name: str = "playwright"
    # Imported after the stage when its own ``junit_xml`` is not set: the
    # first one written (JSON keeps retries and traces, JUnit is the fallback).
    default_junit_xml: tuple[str, ...] = (JSON_RELPATH, JUNIT_RELPATH)

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
            argv.append("--reporter=list,json,html")
        if workers > 0 and not _has_flag(stage_args, "--workers", "-j"):
            argv.append(f"--workers={workers}")
        return argv

    def stage_env(self, *, target_repo: Path, results_dir: Path) -> dict[str, str]:
        # results_dir is <stage>/allure-results/playwright
        stage_dir = results_dir.parent.parent
        repo = target_repo.expanduser().resolve()
        return {
            "PLAYWRIGHT_JSON_OUTPUT_FILE": str(repo / JSON_RELPATH),
            "PLAYWRIGHT_JUNIT_OUTPUT_FILE": str(repo / JUNIT_RELPATH),
            "PLAYWRIGHT_HTML_OUTPUT_DIR": str(stage_dir / HTML_DIRNAME),
            "PLAYWRIGHT_HTML_OPEN": "never",
        }

    def native_report(self, stage_dir: Path) -> NativeReport | None:
        root = stage_dir / HTML_DIRNAME
        if not (root / "index.html").is_file():
            return None
        return NativeReport(root_dir=root, entry_relpath="index.html")
