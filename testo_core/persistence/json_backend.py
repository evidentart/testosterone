"""JSON file persistence backend — writes plan_result.json to the artifacts tree."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from testo_core.engine.result import PlanResult
from testo_core.persistence.health import compute_stage_health, run_test_totals
from testo_core.reporting.paths import plan_artifacts_dir

logger = logging.getLogger(__name__)


class JsonBackend:
    """Write a structured ``plan_result.json`` next to the NDJSON events file."""

    def __init__(self, artifacts_root: Path) -> None:
        self._artifacts_root = artifacts_root

    def persist(self, result: PlanResult) -> None:
        try:
            target = plan_artifacts_dir(self._artifacts_root, result.plan_name) / "plan_result.json"
            target.parent.mkdir(parents=True, exist_ok=True)

            stage_health, health_pct = compute_stage_health(result, self._artifacts_root)
            if health_pct is None and result.stages:
                passed_stages = sum(1 for s in result.stages if s.returncode == 0)
                health_pct = 100.0 * passed_stages / len(result.stages)
            stage_health_by_name = {h["name"]: h for h in stage_health}

            payload = {
                "plan": result.plan_name,
                "target_repo": str(result.target_repo) if result.target_repo is not None else None,
                "started_at": result.started_at,
                "finished_at": result.finished_at,
                "duration_s": result.duration_s,
                "aggregate_returncode": result.aggregate_returncode,
                "exit_code": int(result.exit_code),
                "stages": [
                    {
                        "name": s.stage_name,
                        "framework": s.framework,
                        "tier": s.tier,
                        "returncode": int(s.returncode),
                        "duration_s": s.duration_s,
                        "log_path": str(s.log_path) if s.log_path else None,
                        "timed_out": s.timed_out,
                        "error": s.error,
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
            }
            target.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        except OSError:
            logger.debug("json persistence failed for plan %s", result.plan_name, exc_info=True)
