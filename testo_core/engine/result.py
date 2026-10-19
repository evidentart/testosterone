"""Per-stage and plan-level result dataclasses.

These are intentionally plain dataclasses (no Rich, no Pydantic) so any
consumer — CLI renderer, exporter, FastAPI route — can pass them around
without circular imports.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from testo_core.engine.exit_codes import EngineExitCode


@dataclass(frozen=True)
class StageResult:
    """Outcome of a single stage subprocess."""

    stage_name: str
    framework: str
    returncode: int
    started_at: float
    finished_at: float
    duration_s: float
    log_path: Path | None
    artifacts_dir: Path
    command: tuple[str, ...]
    output_tail: str
    timed_out: bool = False
    error: str | None = None
    internal_failure: bool = False
    # Test-pyramid tier the stage was configured with when it ran. Persisted in the
    # run record so `/runs/{id}/pyramid` doesn't depend on today's YAML.
    tier: str | None = None
    target_repo: Path | None = None


@dataclass(frozen=True)
class PlanResult:
    """Outcome of one :func:`testo_core.engine.orchestrator.run_plan` call."""

    plan_name: str
    started_at: float
    finished_at: float
    duration_s: float
    stages: tuple[StageResult, ...]
    aggregate_returncode: int
    exit_code: EngineExitCode
    error: str | None = None
    failure_type: str | None = None
    extra: dict[str, object] = field(default_factory=dict)
    target_repo: Path | None = None
