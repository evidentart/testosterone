"""Immutable, framework-agnostic dataclasses for the cycle-aware config schema.

The CLI loader produces a :class:`TestosteroneConfig` by parsing YAML or the
``[tool.testosterone]`` table of ``pyproject.toml``.  Down-stream code (the
orchestrator, the report exporter, tests) consumes these objects directly and
never re-parses the source text.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

# Supported frameworks. Add new ones in :mod:`testo_core.frameworks` and append here.
SUPPORTED_FRAMEWORKS: frozenset[str] = frozenset(
    {"pytest", "behave", "behavex", "command", "junit", "playwright"}
)

# Frameworks that act on a stage's ``workers``: BehaveX always (``--parallel-processes``),
# Playwright always (``--workers``), pytest only when pytest-xdist is installed (``-n``).
# The others run single-process.
PARALLEL_FRAMEWORKS: frozenset[str] = frozenset({"pytest", "behavex", "playwright"})

# Test-pyramid tiers a stage's tests are counted under. See `pyramid_data.py`.
SUPPORTED_TIERS: frozenset[str] = frozenset({"unit", "integration", "e2e"})

# Default tier per framework when a stage doesn't set 'tier' explicitly.
DEFAULT_TIER_BY_FRAMEWORK: dict[str, str] = {
    "pytest": "unit",
    "behave": "integration",
    "behavex": "e2e",
    "playwright": "e2e",
    # Any other runner (Jest, Playwright, Maestro, go test, ...): the stage's
    # ``args`` are the whole argv; results come in through ``junit_xml``.
    "command": "unit",
    # Runs nothing: records the JUnit XML its ``junit_xml`` globs match (``testo ingest``).
    "junit": "unit",
}

# Supported post-run reporters. Add new ones in :mod:`testo_core.reporting.reporters` and append here.
SUPPORTED_REPORTER_TYPES: frozenset[str] = frozenset(
    {"allure", "extent", "reportportal", "slack", "teams", "testbeats"}
)


@dataclass(frozen=True)
class Defaults:
    """Repository-wide defaults inherited by every stage unless overridden."""

    target_repo: Path = Path(".")
    artifacts_root: Path = Path("artifacts")
    timeout_s: float | None = 600.0
    workers: int = 4
    extra_env: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class CycleTrigger:
    """Optional selective execution: run the cycle only when matched paths change.

    ``paths`` use pathlib-style globs relative to the config file directory (anchor).
    """

    paths: tuple[str, ...]
    since_ref: str | None = None  # e.g. ``origin/main`` → ``git diff since_ref...HEAD``


@dataclass(frozen=True)
class Stage:
    """One execution step in a plan.

    All path-typed fields are resolved against the config file's directory at
    load time so the orchestrator never has to know where the YAML lives.
    """

    name: str
    framework: str
    target_repo: Path
    args: tuple[str, ...] = ()
    workers: int = 4
    timeout_s: float | None = 600.0
    if_expr: str | None = None
    extra_env: tuple[tuple[str, str], ...] = ()
    tier: str = "unit"
    # Glob patterns (relative to ``target_repo``) of JUnit XML reports the stage
    # writes. After the stage they are converted into Allure ``*-result.json``
    # files in the stage's results dir, so non-Allure runners count in the
    # summaries, health % and reports like any other stage.
    junit_xml: tuple[str, ...] = ()


@dataclass(frozen=True)
class ReporterSpec:
    """One post-run reporter entry from the top-level ``reporters:`` list."""

    type: str
    options: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class Plan:
    """A named sequence of stages executed in order by ``testo run --cycle <name>``."""

    name: str
    description: str | None
    stages: tuple[Stage, ...]
    trigger: CycleTrigger | None = None


@dataclass(frozen=True)
class TestosteroneConfig:
    """Top-level configuration object produced by the loader."""

    version: int
    defaults: Defaults
    cycles: dict[str, Plan] = field(default_factory=dict)
    reporters: tuple[ReporterSpec, ...] = ()
    source_path: Path | None = None

    @property
    def plans(self) -> dict[str, Plan]:
        """Backward-compatible alias for older call sites."""
        return self.cycles
