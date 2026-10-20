"""
Data / infrastructure layer: canonical filesystem layout for the orchestrator.

All path helpers for ``artifacts/`` and ``static/`` should live here so services and
the presentation layer stay DRY and framework-agnostic.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Final

# Overrides where runtime data (``static/``, ``static_reports/``) is written.
DATA_HOME_ENV: Final[str] = "TESTO_HOME"
# Default data directory, under the working directory, for an installed package.
DEFAULT_DATA_DIRNAME: Final[str] = ".testo"


def source_checkout_root(package_dir: Path | None = None) -> Path | None:
    """The repository root when ``testo_core`` runs from a source checkout or editable install.

    A wheel installed into ``site-packages`` has no ``pyproject.toml`` next to it, so this
    returns None there.
    """
    pkg = (package_dir or Path(__file__).resolve().parent).resolve()
    root = pkg.parent
    if (root / "pyproject.toml").is_file() and root.name != "site-packages":
        return root
    return None


def resolve_data_root(*, package_dir: Path | None = None, cwd: Path | None = None) -> Path:
    """Where runtime data lives.

    Precedence: ``$TESTO_HOME`` → the source checkout root (unchanged repo behaviour)
    → ``<cwd>/.testo`` for a ``pip install``, so nothing is written into ``site-packages``.
    """
    override = (os.environ.get(DATA_HOME_ENV) or "").strip()
    if override:
        return Path(override).expanduser().resolve()
    checkout = source_checkout_root(package_dir)
    if checkout is not None:
        return checkout
    return (cwd or Path.cwd()).resolve() / DEFAULT_DATA_DIRNAME


# Resolved once at import, so the CLI and the API use the directory they were started in.
ORCHESTRATOR_ROOT: Final[Path] = resolve_data_root()
STATIC_DIR: Final[Path] = ORCHESTRATOR_ROOT / "static"

# Per-run report bundles (``static/history/<run_id>/``), served by the API at ``/history``.
# Local ``snapshot_dir`` values on run records are relative to ``ORCHESTRATOR_ROOT``.
STATIC_HISTORY_ROOT: Final[Path] = STATIC_DIR / "history"

# Allure HTML output directories (single-file bundle under each directory).
# New layout: ``static/allure_reports/<framework>/index.html``
STATIC_ALLURE_REPORTS_DIR: Final[Path] = STATIC_DIR / "allure_reports"

# Backwards-compatible legacy paths (kept for older snapshots / links).
STATIC_ALLURE_REPORT_DIR: Final[Path] = STATIC_DIR / "allure_report"
STATIC_ALLURE_INDEX: Final[Path] = STATIC_ALLURE_REPORT_DIR / "index.html"
STATIC_ALLURE_HTML: Final[Path] = STATIC_DIR / "allure_report.html"

STATIC_BEHAVE_DIR: Final[Path] = STATIC_DIR / "behave"
STATIC_BEHAVE_INDEX: Final[Path] = STATIC_BEHAVE_DIR / "index.html"

# Under ``<artifacts>/allure-results/`` when using per-framework isolation (audit).
# NOTE:
# - ``behavex``: BehaveX output (kept separate from native Behave)
# - ``behave_native``: standard Behave output
ALLURE_FRAMEWORK_RESULT_SUBDIRS: Final[tuple[str, ...]] = ("pytest", "behavex", "behave_native")


def default_artifacts_root() -> Path:
    """Default relative root for subprocess outputs (resolved by callers when needed)."""
    return Path("artifacts")


def allure_results_dir(artifacts_root: Path) -> Path:
    return artifacts_root.expanduser().resolve() / "allure-results"


def allure_report_dir(framework: str) -> Path:
    """Directory under ``static/allure_reports/<framework>/``."""
    return (STATIC_ALLURE_REPORTS_DIR / str(framework)).resolve()


def allure_framework_result_dirs(artifacts_root: Path) -> tuple[Path, Path, Path]:
    """Per-framework Allure JSON directories (may or may not exist yet)."""
    base = allure_results_dir(artifacts_root)
    return (base / "pytest", base / "behavex", base / "behave_native")


def allure_cli_input_directories(results_dir: Path) -> list[Path]:
    """
    Directories to pass to ``allure generate`` (some CLI builds ignore nested JSON
    when only the parent path is supplied).

    If any of ``pytest/``, ``behavex/``, or ``behave_native/`` exist under ``results_dir``,
    returns each existing subdirectory; otherwise returns ``[results_dir]`` for a
    flat legacy layout.
    """
    results_dir = results_dir.expanduser().resolve()
    subs = [results_dir / name for name in ALLURE_FRAMEWORK_RESULT_SUBDIRS]
    existing = [p for p in subs if p.is_dir()]
    if existing:
        return existing
    return [results_dir] if results_dir.is_dir() else []


@dataclass(frozen=True)
class ArtifactLayout:
    """
    Resolved layout for a given artifacts root (typically ``./artifacts`` from the
    orchestrator working directory).
    """

    artifacts_root: Path

    def __post_init__(self) -> None:
        object.__setattr__(self, "artifacts_root", self.artifacts_root.expanduser().resolve())

    @property
    def allure_results(self) -> Path:
        return self.artifacts_root / "allure-results"

    @property
    def allure_results_archive(self) -> Path:
        return self.artifacts_root / "allure-results-archive"

    @property
    def behave_reports_dir(self) -> Path:
        return self.artifacts_root / "behave_reports"

    def framework_allure_dir(self, name: str) -> Path:
        return self.allure_results / name
