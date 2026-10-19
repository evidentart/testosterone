"""Framework adapter protocol + registry.

Adapters live in tiny modules so adding support for a new framework is a
single-file change with zero impact on the orchestrator.  The executor only
sees the protocol; framework-specific knobs stay encapsulated.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class NativeReport:
    """A framework's own report bundle: a directory to copy wholesale, plus
    the relative path to its entry HTML file within that directory."""

    root_dir: Path
    entry_relpath: str


class FrameworkAdapter(Protocol):
    """Minimum surface required to schedule a stage."""

    name: str

    def results_subdir(self) -> str:
        """Subdirectory under ``<artifacts>/<plan>/<stage>/allure-results/``."""
        ...

    def build_argv(
        self,
        *,
        target_repo: Path,
        results_dir: Path,
        stage_args: tuple[str, ...],
        workers: int,
    ) -> list[str]:
        """Return the argv that should be passed to :class:`subprocess.Popen`."""
        ...

    def native_report(self, stage_dir: Path) -> NativeReport | None:
        """This framework's own native report, if it produces one distinct
        from its Allure JSON export. ``None`` for frameworks with no native
        report format of their own."""
        ...


def get_adapter(framework: str) -> FrameworkAdapter:
    """Return the registered adapter for ``framework``.

    Built-in names are checked first, then ``testo.frameworks`` entry points
    (:mod:`testo_core.plugins`). Imports are kept inside this function so adding a new framework cannot
    break ``testo --help`` import-time performance.
    """
    if framework == "pytest":
        from testo_core.frameworks.pytest_adapter import PytestAdapter

        return PytestAdapter()
    if framework == "behave":
        from testo_core.frameworks.behave_adapter import BehaveAdapter

        return BehaveAdapter()
    if framework == "behavex":
        from testo_core.frameworks.behavex_adapter import BehaveXAdapter

        return BehaveXAdapter()
    if framework == "command":
        from testo_core.frameworks.command_adapter import CommandAdapter

        return CommandAdapter()
    if framework == "playwright":
        from testo_core.frameworks.playwright_adapter import PlaywrightAdapter

        return PlaywrightAdapter()

    from testo_core import plugins

    if framework in plugins.framework_names():
        return plugins.load_framework(framework)
    raise ValueError(f"Unsupported framework: {framework!r}")
