"""Database persistence backend — upserts a RunRecord via the repository layer."""

from __future__ import annotations

import logging
import os
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from testo_core import paths
from testo_core.engine.result import PlanResult
from testo_core.persistence.failure_context import failure_metadata
from testo_core.persistence.health import compute_stage_health, run_test_totals
from testo_core.reporting.paths import plan_artifacts_dir
from testo_core.repository.models import RunStatus

logger = logging.getLogger(__name__)


class DbBackend:
    """Persist a :class:`PlanResult` as a :class:`RunRecord` in the database."""

    def __init__(self, artifacts_root: Path) -> None:
        self._artifacts_root = artifacts_root

    def _local_snapshot_dir(self, plan_name: str) -> str | None:
        """Path of this plan's artifacts relative to ``paths.ORCHESTRATOR_ROOT`` (the data root).

        ``history.snapshots`` reads local ``snapshot_dir`` values relative to
        ``ORCHESTRATOR_ROOT``, so only return a value when the artifacts live under it.
        """
        plan_dir = plan_artifacts_dir(self._artifacts_root, plan_name)
        try:
            return plan_dir.relative_to(paths.ORCHESTRATOR_ROOT).as_posix()
        except ValueError:
            return None

    def _snapshot_run_artifacts(self, run_id: str, plan_name: str) -> str | None:
        """Copy this plan's artifacts to ``static/history/<run_id>/artifacts/``.

        Every run of a cycle writes into the same ``<artifacts>/<cycle>/`` tree,
        so a record pointing there would describe whichever run came last. A
        per-run copy keeps each run's per-test results (Compare's test-level
        diff, the artifact download) after the next run overwrites the tree.
        Returns the copy's path relative to ``ORCHESTRATOR_ROOT``, or None.
        """
        plan_dir = plan_artifacts_dir(self._artifacts_root, plan_name)
        if not plan_dir.is_dir():
            return None
        dest = paths.STATIC_HISTORY_ROOT / run_id / "artifacts"
        try:
            shutil.copytree(plan_dir, dest, dirs_exist_ok=True)
            return dest.relative_to(paths.ORCHESTRATOR_ROOT).as_posix()
        except (OSError, ValueError):
            logger.debug("could not snapshot artifacts for run %s", run_id, exc_info=True)
            return None

    def _record_run_snapshot(self, repo: Any, run_id: str, plan_name: str) -> None:
        """Point the run record at its own copy; it keeps the shared path otherwise."""
        snapshot_dir = self._snapshot_run_artifacts(run_id, plan_name)
        if not snapshot_dir:
            return
        try:
            repo.merge_run_metadata(run_id, {"snapshot_dir": snapshot_dir})
        except Exception:
            # Broad on purpose: the run row already exists; losing this pointer must not lose its id.
            logger.warning("could not record snapshot for run %s", run_id, exc_info=True)

    def persist(self, result: PlanResult) -> str | None:
        try:
            from testo_core.repository.db import get_repository
            from testo_core.services.ci_provenance import detect_ci_provenance

            repo = get_repository()
            status = RunStatus.COMPLETED if result.exit_code == 0 else RunStatus.FAILED

            stage_health, health_pct = compute_stage_health(result, self._artifacts_root)
            if health_pct is None and result.stages:
                passed_stages = sum(1 for s in result.stages if s.returncode == 0)
                health_pct = 100.0 * passed_stages / len(result.stages)
            stage_health_by_name = {h["name"]: h for h in stage_health}
            provenance = detect_ci_provenance(os.environ)
            extra_metadata = result.extra.get("run_metadata")

            record = repo.create_run(
                status=status,
                metadata={
                    "plan": result.plan_name,
                    "target_repo": str(result.target_repo)
                    if result.target_repo is not None
                    else None,
                    "test_kind": "cycle",
                    "returncode": int(result.exit_code),
                    "exit_code": int(result.exit_code),
                    "aggregate_returncode": result.aggregate_returncode,
                    "duration_s": result.duration_s,
                    "started_at": result.started_at,
                    "finished_at": result.finished_at,
                    "started_at_iso": datetime.fromtimestamp(result.started_at, tz=UTC).isoformat(),
                    "stage_count": len(result.stages),
                    "stages": [
                        {
                            "name": s.stage_name,
                            "framework": s.framework,
                            "tier": s.tier,
                            "returncode": s.returncode,
                            "duration_s": s.duration_s,
                            "quarantined": list(s.quarantined),
                            "waived_returncode": s.waived_returncode,
                            **{
                                k: v
                                for k, v in stage_health_by_name.get(s.stage_name, {}).items()
                                if k != "name"
                            },
                        }
                        for s in result.stages
                    ],
                    "health_pct": health_pct,
                    **run_test_totals(stage_health),
                    "snapshot_dir": self._local_snapshot_dir(result.plan_name),
                    "source": "engine",
                    **failure_metadata(result),
                    **(provenance.to_metadata() if provenance else {}),
                    **(extra_metadata if isinstance(extra_metadata, dict) else {}),
                },
            )
            run_id = str(record.id)
            self._record_run_snapshot(repo, run_id, result.plan_name)
            return run_id
        except Exception:
            # Broad on purpose: DB history is best-effort; the JSON backend still has the run.
            logger.warning("db persistence failed for plan %s", result.plan_name, exc_info=True)
            return None
