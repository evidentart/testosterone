"""Tests for :mod:`testo_core.reporting.behavex_allure`.

The end-to-end path (real ``behavex``, both reports) is covered by
``tests/integration/testo_core/engine/test_behavex_reports.py``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from testo_core.reporting.behavex_allure import export_behavex_allure_results

pytestmark = [pytest.mark.unit, pytest.mark.tier_fast]


def test_nothing_to_export_without_report_json(tmp_path: Path) -> None:
    results_dir = tmp_path / "allure-results" / "behavex"

    assert export_behavex_allure_results(tmp_path / "behave_reports", results_dir) is None
    assert not results_dir.exists()


def test_existing_results_are_left_alone(tmp_path: Path) -> None:
    """A stage that passed its own ``--formatter`` already wrote Allure results."""
    report_dir = tmp_path / "behave_reports"
    report_dir.mkdir()
    (report_dir / "report.json").write_text('{"features": []}', encoding="utf-8")
    results_dir = tmp_path / "allure-results" / "behavex"
    results_dir.mkdir(parents=True)
    (results_dir / "abc-result.json").write_text("{}", encoding="utf-8")

    assert export_behavex_allure_results(report_dir, results_dir) is None
    assert [p.name for p in results_dir.iterdir()] == ["abc-result.json"]


def test_unreadable_report_raises(tmp_path: Path) -> None:
    report_dir = tmp_path / "behave_reports"
    report_dir.mkdir()
    (report_dir / "report.json").write_text("{truncated", encoding="utf-8")

    with pytest.raises(ValueError):
        export_behavex_allure_results(report_dir, tmp_path / "allure-results" / "behavex")
