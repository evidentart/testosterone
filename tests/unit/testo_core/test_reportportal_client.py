"""ReportPortal client unit tests with mocked HTTP."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from testo_core.reporting.allure_results import RunAggregate, StageSummary, TestCaseRecord
from testo_core.reporting.reporters.reportportal_client import (
    ReportPortalClient,
    ReportPortalError,
)


def _minimal_aggregate() -> RunAggregate:
    stage = StageSummary(
        plan="p",
        stage="s",
        framework="pytest",
        total=1,
        passed=1,
        failed=0,
        broken=0,
        skipped=0,
        duration_ms=100,
    )
    test = TestCaseRecord(
        id="abc",
        name="test_one",
        full_name="test_one",
        status="passed",
        duration_ms=100,
        plan="p",
        stage="s",
        framework="pytest",
        description=None,
        failure_message=None,
        start_ms=1000,
        stop_ms=1100,
    )
    return RunAggregate(
        artifacts_root="/tmp",
        total=1,
        passed=1,
        failed=0,
        broken=0,
        skipped=0,
        duration_ms=100,
        stages=(stage,),
        tests=(test,),
    )


def _mock_response(*, status: int = 200, payload: dict | None = None) -> MagicMock:
    resp = MagicMock(status_code=status)
    resp.text = ""
    resp.json.return_value = payload or {}
    return resp


def test_detect_api_version_falls_back_to_v1() -> None:
    session = MagicMock()
    session.headers = {}
    session.get.side_effect = [
        _mock_response(status=404),
        _mock_response(status=200),
    ]

    with patch(
        "testo_core.reporting.reporters.reportportal_client.requests.Session",
        return_value=session,
    ):
        client = ReportPortalClient("http://rp.local", "proj", "token")
    assert client.api_version == "v1"


def test_report_aggregate_calls_launch_and_items() -> None:
    session = MagicMock()
    session.headers = {}
    session.get.return_value = _mock_response()

    def post_side_effect(url, **kwargs):
        if url.endswith("/launch"):
            return _mock_response(payload={"id": "launch-uuid-1"})
        return _mock_response(payload={"id": "item-uuid-1"})

    session.post.side_effect = post_side_effect
    session.put.return_value = _mock_response()

    with patch(
        "testo_core.reporting.reporters.reportportal_client.requests.Session",
        return_value=session,
    ):
        client = ReportPortalClient("http://rp.local", "proj", "token", api_version="v1")
        launch_id = client.report_aggregate(_minimal_aggregate(), launch_name="run-1")

    assert launch_id
    first_post_url = session.post.call_args_list[0][0][0]
    assert first_post_url.endswith("/launch")
    assert session.post.call_count >= 2
    assert session.put.call_count >= 2


def test_report_aggregate_uses_earliest_test_start_for_launch() -> None:
    """Launch startTime must not be later than child test startTime (ReportPortal 40025)."""
    session = MagicMock()
    session.headers = {}
    session.get.return_value = _mock_response()
    launch_bodies: list[dict] = []

    def post_side_effect(url, **kwargs):
        if url.endswith("/launch"):
            launch_bodies.append(kwargs.get("json") or {})
            return _mock_response(payload={"id": "launch-uuid-1"})
        return _mock_response(payload={"id": "item-uuid-1"})

    session.post.side_effect = post_side_effect
    session.put.return_value = _mock_response()

    aggregate = _minimal_aggregate()  # test start_ms=1000, stop_ms=1100

    with (
        patch(
            "testo_core.reporting.reporters.reportportal_client.requests.Session",
            return_value=session,
        ),
        patch(
            "testo_core.reporting.reporters.reportportal_client._now_ms",
            return_value=9_999_999,
        ),
    ):
        client = ReportPortalClient("http://rp.local", "proj", "token", api_version="v1")
        client.report_aggregate(aggregate, launch_name="run-1")

    assert launch_bodies
    assert launch_bodies[0]["startTime"] == "1000"


def test_validate_raises_on_401() -> None:
    session = MagicMock()
    session.headers = {}
    session.get.return_value = _mock_response(status=401)

    with patch(
        "testo_core.reporting.reporters.reportportal_client.requests.Session",
        return_value=session,
    ):
        client = ReportPortalClient("http://rp.local", "proj", "bad", api_version="v1")
        with pytest.raises(ReportPortalError, match="authentication"):
            client.validate()
