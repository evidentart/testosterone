"""Concrete renderers that consume :mod:`testo_core.engine.events`.

Three implementations are provided:

* :class:`BufferedRenderer` (default) — live Rich progress while the stage
  runs, then a post-mortem panel after it exits.  This is the "Locust Model"
  the user asked for: no scrambled log lines on the terminal.
* :class:`StreamRenderer` (``--stream``) — same panels, but log lines are
  flushed live as the stage runs.  Useful for debugging hung tests.
* :class:`CIRenderer` (``--ci``) — pure NDJSON events on stdout, no ANSI,
  no panels.  Designed for CI log tailers (GitHub Actions, GitLab CI).
"""

from __future__ import annotations

import logging
from contextlib import AbstractContextManager, nullcontext
from typing import Protocol

from rich.console import Console
from rich.progress import Progress

from testo_core.cli.ui.ci_renderer import emit_ndjson
from testo_core.cli.ui.panels import StagePanelData, render_plan_summary, render_stage_panel
from testo_core.cli.ui.progress import stage_progress
from testo_core.engine.events import (
    EngineEvent,
    PlanFinished,
    PlanStarted,
    StageFinished,
    StageOutputChunk,
    StageStarted,
)

logger = logging.getLogger(__name__)


class Renderer(Protocol):
    """Protocol consumed by :func:`testo_core.engine.orchestrator.run_plan`."""

    wants_streaming: bool

    def handle(self, event: EngineEvent) -> None: ...


class BufferedRenderer:
    """Default human renderer: live progress, post-mortem panels."""

    wants_streaming: bool = False

    def __init__(self, console: Console, *, output_tail_lines: int = 80) -> None:
        self._console = console
        self._tail_lines = output_tail_lines
        self._panels: list[StagePanelData] = []
        self._progress_ctx: AbstractContextManager[Progress | None] = nullcontext()
        self._progress: Progress | None = None

    def handle(self, event: EngineEvent) -> None:
        if isinstance(event, PlanStarted):
            self._console.rule(f"[title]Cycle:[/] {event.plan.name}", style="title")
        elif isinstance(event, StageStarted):
            label = f"[{event.stage_index}/{event.stage_count}] {event.stage.name} ({event.stage.framework})"
            self._progress_ctx = stage_progress(self._console, label=label)
            self._progress = self._progress_ctx.__enter__()
        elif isinstance(event, StageFinished):
            self._close_progress()
            panel = _panel_from_result(event.result)
            self._panels.append(panel)
            render_stage_panel(self._console, panel, tail_max_lines=self._tail_lines)
        elif isinstance(event, PlanFinished):
            self._close_progress()
            render_plan_summary(
                self._console,
                plan_name=event.result.plan_name,
                stage_results=self._panels,
                aggregate_returncode=event.result.aggregate_returncode,
            )
            if event.result.error:
                self._console.print(f"[fail]error:[/] {event.result.error}")

    def _close_progress(self) -> None:
        if self._progress is not None:
            self._progress_ctx.__exit__(None, None, None)
            self._progress = None
            self._progress_ctx = nullcontext()


class StreamRenderer(BufferedRenderer):
    """Same panels as :class:`BufferedRenderer`, but tails log chunks live."""

    wants_streaming: bool = True

    def handle(self, event: EngineEvent) -> None:
        if isinstance(event, StageOutputChunk):
            text = event.chunk.decode("utf-8", errors="replace")
            self._console.out(text, end="", highlight=False)
            return
        super().handle(event)


class CIRenderer:
    """NDJSON event emitter for ``--ci``.

    Each event becomes one JSON line on stdout.  Stage output chunks are not
    emitted by default (too noisy); CI consumers should read the per-stage
    log files from ``artifacts/<plan>/<stage>/run.log`` instead.
    """

    wants_streaming: bool = False

    def __init__(self) -> None:
        self._stages: list[dict[str, object]] = []

    def handle(self, event: EngineEvent) -> None:
        if isinstance(event, PlanStarted):
            emit_ndjson(
                {
                    "event": "plan_started",
                    "plan": event.plan.name,
                    "stage_count": len(event.plan.stages),
                }
            )
        elif isinstance(event, StageStarted):
            emit_ndjson(
                {
                    "event": "stage_started",
                    "stage": event.stage.name,
                    "framework": event.stage.framework,
                    "index": event.stage_index,
                    "count": event.stage_count,
                }
            )
        elif isinstance(event, StageFinished):
            stage_payload = {
                "stage": event.result.stage_name,
                "framework": event.result.framework,
                "returncode": int(event.result.returncode),
                "duration_s": float(event.result.duration_s),
                "log_path": str(event.result.log_path) if event.result.log_path else None,
                "timed_out": bool(event.result.timed_out),
                "quarantined": list(event.result.quarantined),
                "waived_returncode": event.result.waived_returncode,
            }
            self._stages.append(stage_payload)
            emit_ndjson({"event": "stage_finished", **stage_payload})
        elif isinstance(event, PlanFinished):
            emit_ndjson(
                {
                    "event": "plan_finished",
                    "plan": event.result.plan_name,
                    "aggregate_returncode": int(event.result.aggregate_returncode),
                    "exit_code": int(event.result.exit_code),
                    "duration_s": float(event.result.duration_s),
                    "stages": self._stages,
                    "error": event.result.error,
                }
            )


def _panel_from_result(result) -> StagePanelData:  # type: ignore[no-untyped-def]
    # Executor layout contract:
    #   <artifacts>/<cycle>/<stage>/allure-results/<equipment>/
    results_dir = None
    try:
        artifacts_dir = getattr(result, "artifacts_dir", None)
        if artifacts_dir is not None:
            results_dir = str((artifacts_dir / "allure-results" / str(result.framework)).resolve())
    except OSError:
        logger.debug("could not resolve results dir for %s", result.stage_name, exc_info=True)
        results_dir = None
    return StagePanelData(
        name=result.stage_name,
        framework=result.framework,
        returncode=int(result.returncode),
        duration_s=float(result.duration_s),
        log_path=str(result.log_path) if result.log_path else None,
        output_tail=result.output_tail,
        results_dir=results_dir,
        command=" ".join(result.command),
        quarantined=tuple(getattr(result, "quarantined", ())),
        error=getattr(result, "error", None),
    )
