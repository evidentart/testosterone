from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from testo_api.models import (
    DeltaCaseChange,
    DeltaCaseChangesResponse,
    DeltaComparisonMeta,
    DeltaComparisonResponse,
    DeltaMetricNode,
    DeltaMetricsResponse,
    DeltaPerformanceMetrics,
    DeltaReliabilityMetrics,
    DeltaStageDelta,
    DeltaStatusSummaryResponse,
    FlakyTestItem,
    FlakyTestsResponse,
)
from testo_core.history.read_model import get_run
from testo_core.services.delta_models import MetricDelta
from testo_core.services.delta_service import (
    DeltaComparisonService,
    IncompatibleRunDataError,
    InvalidRunIdError,
    RunNotFoundComparisonError,
)
from testo_core.services.flaky_service import DEFAULT_WINDOW, find_flaky_tests
from testo_core.services.run_snapshot_diff import diff_run_snapshots

router = APIRouter(prefix="/api/v1", tags=["analytics"])


@router.get("/analytics/delta", response_model=DeltaComparisonResponse)
def get_delta_comparison(current_run_id: str, baseline_run_id: str) -> DeltaComparisonResponse:
    service = DeltaComparisonService()
    try:
        result = service.compare_runs(
            current_run_id=current_run_id, baseline_run_id=baseline_run_id
        )
    except InvalidRunIdError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RunNotFoundComparisonError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except IncompatibleRunDataError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    metric_map = {metric.metric_key: metric for metric in result.metrics}
    return DeltaComparisonResponse(
        comparison=DeltaComparisonMeta(
            current_run_id=result.current_run_id,
            baseline_run_id=result.baseline_run_id,
            current_test_kind=result.current_test_kind,
            baseline_test_kind=result.baseline_test_kind,
        ),
        metrics=DeltaMetricsResponse(
            reliability=DeltaReliabilityMetrics(
                total_tests=_to_metric_node(metric_map["total_tests"]),
                passed=_to_metric_node(metric_map["passed"]),
                failed=_to_metric_node(metric_map["failed"]),
                broken=_to_metric_node(metric_map["broken"]),
                skipped=_to_metric_node(metric_map["skipped"]),
                health_pct=_to_metric_node(metric_map["health_pct"]),
            ),
            performance=DeltaPerformanceMetrics(
                wall_duration_ms=_to_metric_node(metric_map["wall_duration_ms"]),
                metrics_duration_ms=_to_metric_node(metric_map["metrics_duration_ms"]),
                avg_case_ms=_to_metric_node(metric_map["avg_case_ms"]),
            ),
        ),
        status_summary=DeltaStatusSummaryResponse(
            regressions=list(result.status_summary.regressions),
            improvements=list(result.status_summary.improvements),
            unchanged=list(result.status_summary.unchanged),
            unknown=list(result.status_summary.unknown),
        ),
        highlights=list(result.highlights),
        stage_deltas=[
            DeltaStageDelta(
                stage_name=sd.stage_name,
                framework=sd.framework,
                baseline_total_tests=sd.baseline_total_tests,
                current_total_tests=sd.current_total_tests,
                baseline_passed=sd.baseline_passed,
                current_passed=sd.current_passed,
                baseline_health_pct=sd.baseline_health_pct,
                current_health_pct=sd.current_health_pct,
                health_pct_delta=sd.health_pct_delta,
                classification=sd.classification,
            )
            for sd in result.stage_deltas
        ],
    )


def _to_metric_node(metric: MetricDelta) -> DeltaMetricNode:
    return DeltaMetricNode(
        current_value=metric.current_value,
        baseline_value=metric.baseline_value,
        absolute_delta=metric.absolute_delta,
        relative_delta_pct=metric.relative_delta_pct,
        classification=metric.classification,
        reason=metric.reason,
        direction=metric.direction,
        unit=metric.unit,
    )


@router.get("/analytics/delta/cases", response_model=DeltaCaseChangesResponse)
def get_delta_case_changes(current_run_id: str, baseline_run_id: str) -> DeltaCaseChangesResponse:
    """Per-test added/removed/regression/fix breakdown -- UI parity with ``testo diff``.

    Computed on-demand from each run's own artifact snapshot every request (no
    caching): extracts both snapshots into a temp dir and matches cases by
    historyId/fullName/uuid, same as the CLI's full (non ``--metrics-only``) diff.
    """
    import tempfile
    from pathlib import Path

    current = get_run(run_id=current_run_id)
    if current is None:
        raise HTTPException(status_code=404, detail=f"Run not found: {current_run_id}")
    baseline = get_run(run_id=baseline_run_id)
    if baseline is None:
        raise HTTPException(status_code=404, detail=f"Run not found: {baseline_run_id}")

    with tempfile.TemporaryDirectory(prefix="testo-api-diff-") as td:
        changes = diff_run_snapshots(baseline=baseline, current=current, tmp=Path(td))

    return DeltaCaseChangesResponse(
        current_run_id=current_run_id,
        baseline_run_id=baseline_run_id,
        changes=[
            DeltaCaseChange(
                key=c.key,
                name=c.name,
                group=c.group,
                baseline_status=c.baseline_status,
                current_status=c.current_status,
                kind=c.kind,
                duration_delta_ms=c.duration_delta_ms,
            )
            for c in changes
        ],
    )


@router.get("/analytics/flaky", response_model=FlakyTestsResponse)
def get_flaky_tests(
    cycle: str, window: int = Query(DEFAULT_WINDOW, ge=2, le=200)
) -> FlakyTestsResponse:
    """Tests that both passed and failed, flipping at least twice, in a cycle's last runs.

    UI parity with ``testo flaky --cycle``; see ``testo_core/services/flaky_service.py``.
    """
    report = find_flaky_tests(cycle=cycle, window=window)
    return FlakyTestsResponse(
        cycle=report.cycle,
        window=report.window,
        runs_analyzed=report.runs_analyzed,
        tests_analyzed=report.tests_analyzed,
        items=[
            FlakyTestItem(
                key=t.key,
                name=t.name,
                group=t.group,
                runs=t.runs,
                passed=t.passed,
                failed=t.failed,
                flips=t.flips,
                flip_rate=t.flip_rate,
                last_status=t.last_status,
                history=list(t.history),
            )
            for t in report.flaky
        ],
    )
