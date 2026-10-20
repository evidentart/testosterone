"""Docker-layout artifact collection."""

from __future__ import annotations

import json
from pathlib import Path

from testo_core.reporting.collector import collect_results_docker_run


def test_collect_results_docker_run_flat_layout(tmp_path: Path) -> None:
    fw_dir = tmp_path / "allure-results" / "pytest"
    fw_dir.mkdir(parents=True)
    (fw_dir / "x-result.json").write_text(
        json.dumps({"name": "t", "status": "passed"}), encoding="utf-8"
    )

    collected = collect_results_docker_run(tmp_path, run_id="run-1")
    assert len(collected.stages) == 1
    assert collected.stages[0].framework == "pytest"
    assert collected.stages[0].plan == "run-1"
