"""Orchestration entry point for configured reporters."""

from __future__ import annotations

import json
from pathlib import Path

from testo_core.config import schema as config_schema
from testo_core.config.schema import Defaults, ReporterSpec
from testo_core.reporting.reporters.orchestrate import run_configured_reporters


def _write_allure_result(results_dir: Path) -> None:
    results_dir.mkdir(parents=True, exist_ok=True)
    (results_dir / "abc-result.json").write_text(
        json.dumps(
            {
                "name": "test_one",
                "status": "passed",
                "start": 1,
                "stop": 2,
            }
        ),
        encoding="utf-8",
    )


def test_run_configured_reporters_extent_stub(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    plan_dir = artifacts / "smoke" / "stage1" / "allure-results" / "pytest"
    _write_allure_result(plan_dir)

    cfg = config_schema.TestosteroneConfig(
        version=1,
        defaults=Defaults(artifacts_root=artifacts),
        cycles={},
        reporters=(
            ReporterSpec(type="extent", options=(("output_dir", str(tmp_path / "extent")),)),
        ),
    )
    outcomes = run_configured_reporters(
        cfg=cfg,
        artifacts_root=artifacts,
        plan_name="smoke",
        generate_only=True,
    )
    assert len(outcomes) == 1
    assert outcomes[0].ok
    assert (tmp_path / "extent" / "index.html").is_file()


def test_run_configured_reporters_noop_when_empty() -> None:
    cfg = config_schema.TestosteroneConfig(version=1, defaults=Defaults(), cycles={}, reporters=())
    assert run_configured_reporters(cfg=cfg, artifacts_root=Path("/tmp")) == []
