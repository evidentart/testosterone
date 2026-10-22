"""Reporter registry and factory."""

from __future__ import annotations

import logging
import os
from collections.abc import Sequence
from typing import TYPE_CHECKING

from testo_core import plugins
from testo_core.config.resolver import _interpolate
from testo_core.config.schema import ReporterSpec
from testo_core.reporting.collector import CollectedResults
from testo_core.reporting.reporters.alert_reporter import SlackReporter, TeamsReporter
from testo_core.reporting.reporters.allure_reporter import AllureReporter
from testo_core.reporting.reporters.base import BaseReporter, ReportContext, ReporterResult
from testo_core.reporting.reporters.extent_reporter import ExtentReporter
from testo_core.reporting.reporters.reportportal_reporter import ReportPortalReporter
from testo_core.reporting.reporters.testbeats_reporter import TestBeatsReporter

if TYPE_CHECKING:
    from rich.console import Console

logger = logging.getLogger(__name__)

_REPORTER_REGISTRY: dict[str, type[BaseReporter]] = {
    "allure": AllureReporter,
    "extent": ExtentReporter,
    "reportportal": ReportPortalReporter,
    "slack": SlackReporter,
    "teams": TeamsReporter,
    "testbeats": TestBeatsReporter,
}


def resolve_active_reporter_specs(
    config_reporters: tuple[ReporterSpec, ...],
    *,
    overrides: Sequence[str] | None,
) -> tuple[ReporterSpec, ...]:
    """CLI ``--reporter`` replaces YAML when overrides are provided."""
    if overrides:
        normalised: list[ReporterSpec] = []
        for token in overrides:
            t = str(token).strip().lower()
            if not t:
                continue
            supported = plugins.reporter_types()
            if t not in supported:
                raise ValueError(f"unsupported reporter type {t!r}; supported: {sorted(supported)}")
            normalised.append(ReporterSpec(type=t, options=()))
        return tuple(normalised)
    return config_reporters


def _interpolate_options(options: dict[str, str]) -> dict[str, str]:
    env = os.environ
    return {k: _interpolate(v, env=env) for k, v in options.items()}


class ReporterFactory:
    """Build and run reporter instances from config specs."""

    @staticmethod
    def build(
        *,
        config_reporters: tuple[ReporterSpec, ...],
        overrides: Sequence[str] | None = None,
    ) -> list[BaseReporter]:
        active = resolve_active_reporter_specs(config_reporters, overrides=overrides)

        reporters: list[BaseReporter] = []
        for spec in active:
            cls = _REPORTER_REGISTRY.get(spec.type)
            if cls is None:
                supported = plugins.reporter_types()
                if spec.type not in supported:
                    raise ValueError(
                        f"unsupported reporter type {spec.type!r}; supported: {sorted(supported)}"
                    )
                cls = plugins.load_reporter(spec.type)
            opts = _interpolate_options(dict(spec.options))
            reporters.append(cls(options=opts))
        return reporters

    @staticmethod
    def run_all(
        reporters: Sequence[BaseReporter],
        *,
        results: CollectedResults,
        context: ReportContext,
        console: Console | None = None,
    ) -> list[ReporterResult]:
        """Run reporters: Allure first (sequential), then others in parallel."""
        if not reporters:
            return []

        allure = [r for r in reporters if r.reporter_type == "allure"]
        others = [r for r in reporters if r.reporter_type != "allure"]
        outcomes: list[ReporterResult] = []

        for reporter in allure:
            outcomes.append(reporter.publish(results=results, context=context, console=console))

        if not others:
            return outcomes

        from concurrent.futures import ThreadPoolExecutor, as_completed

        with ThreadPoolExecutor(max_workers=len(others)) as pool:
            futures = {
                pool.submit(r.publish, results=results, context=context, console=console): r
                for r in others
            }
            for future in as_completed(futures):
                try:
                    outcomes.append(future.result())
                except Exception as exc:
                    # Broad on purpose: one broken reporter must not stop the others.
                    reporter = futures[future]
                    logger.warning("%s reporter failed", reporter.reporter_type, exc_info=True)
                    outcomes.append(
                        ReporterResult(
                            ok=False,
                            message=f"{reporter.reporter_type} failed: {exc}",
                        )
                    )
        return outcomes
