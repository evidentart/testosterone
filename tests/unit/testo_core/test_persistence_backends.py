"""Unit tests for testo_core.persistence backends (Sprint 3 — Task 3.1.7)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from testo_core.engine.exit_codes import EngineExitCode
from testo_core.engine.result import PlanResult, StageResult
from testo_core.persistence.backend import PersistenceBackend
from testo_core.persistence.composite import composite_backend
from testo_core.persistence.db_backend import DbBackend
from testo_core.persistence.json_backend import JsonBackend


@pytest.fixture(autouse=True)
def _isolated_static_history(monkeypatch: pytest.MonkeyPatch, tmp_path_factory) -> None:  # noqa: ANN001
    """Per-run snapshots are copied under ``STATIC_HISTORY_ROOT``; keep them out of the repo."""
    monkeypatch.setattr(
        "testo_core.paths.STATIC_HISTORY_ROOT", tmp_path_factory.mktemp("static_history")
    )


def _make_plan_result(
    plan_name: str = "smoke",
    exit_code: EngineExitCode = EngineExitCode.SUCCESS,
    artifacts_dir: Path = Path("artifacts/smoke"),
    target_repo: Path | None = None,
) -> PlanResult:
    stage = StageResult(
        stage_name="api",
        framework="pytest",
        returncode=0 if exit_code == EngineExitCode.SUCCESS else 1,
        started_at=1000.0,
        finished_at=1002.5,
        duration_s=2.5,
        log_path=Path("artifacts/smoke/api.log"),
        artifacts_dir=artifacts_dir,
        command=("pytest", "-q"),
        output_tail="1 passed",
        timed_out=False,
        tier="integration",
    )
    return PlanResult(
        plan_name=plan_name,
        started_at=1000.0,
        finished_at=1002.5,
        duration_s=2.5,
        stages=(stage,),
        aggregate_returncode=stage.returncode,
        exit_code=exit_code,
        target_repo=target_repo,
    )


def _write_allure_result(results_dir: Path, name: str, status: str, duration_ms: int = 1) -> None:
    results_dir.mkdir(parents=True, exist_ok=True)
    start = 1_700_000_000_000
    payload = {
        "name": name,
        "fullName": name,
        "status": status,
        "start": start,
        "stop": start + duration_ms,
    }
    (results_dir / f"{name}-result.json").write_text(json.dumps(payload), encoding="utf-8")


def _write_timed_results(stage_dir: Path) -> None:
    """Three tests taking 100 + 200 + 300 ms: 600 ms of test time, 200 ms per test."""
    results_dir = stage_dir / "allure-results" / "pytest"
    _write_allure_result(results_dir, "test_one", "passed", duration_ms=100)
    _write_allure_result(results_dir, "test_two", "passed", duration_ms=200)
    _write_allure_result(results_dir, "test_three", "failed", duration_ms=300)


class TestJsonBackend:
    def test_satisfies_protocol(self) -> None:
        backend = JsonBackend(Path("/tmp"))
        assert isinstance(backend, PersistenceBackend)

    def test_writes_plan_result_json(self, tmp_path: Path) -> None:
        backend = JsonBackend(tmp_path)
        result = _make_plan_result(target_repo=tmp_path)
        backend.persist(result)

        out = tmp_path / "smoke" / "plan_result.json"
        assert out.exists()
        data = json.loads(out.read_text())
        assert data["plan"] == "smoke"
        assert data["target_repo"] == str(tmp_path)
        assert data["exit_code"] == 0
        assert len(data["stages"]) == 1
        assert data["stages"][0]["name"] == "api"
        assert data["stages"][0]["tier"] == "integration"

    def test_writes_failure_exit_code(self, tmp_path: Path) -> None:
        backend = JsonBackend(tmp_path)
        result = _make_plan_result(exit_code=EngineExitCode.DOMAIN_FAILURE)
        backend.persist(result)

        data = json.loads((tmp_path / "smoke" / "plan_result.json").read_text())
        assert data["exit_code"] == 1
        assert data["target_repo"] is None
        assert data["stages"][0]["returncode"] == 1

    def test_silently_handles_write_error(self, tmp_path: Path) -> None:
        backend = JsonBackend(Path("/nonexistent/deeply/nested/path"))
        result = _make_plan_result()
        backend.persist(result)

    def test_health_pct_is_real_pass_rate_not_binary_returncode(self, tmp_path: Path) -> None:
        """A stage subprocess can exit non-zero (one test failed) while most
        tests in it passed — health_pct must reflect the real pass rate
        (2/3 = 66.67%), not the binary 0% a returncode-only estimate gives."""
        stage_dir = tmp_path / "stage" / "api"
        results_dir = stage_dir / "allure-results" / "pytest"
        _write_allure_result(results_dir, "test_one", "passed")
        _write_allure_result(results_dir, "test_two", "passed")
        _write_allure_result(results_dir, "test_three", "failed")

        backend = JsonBackend(tmp_path)
        result = _make_plan_result(exit_code=EngineExitCode.DOMAIN_FAILURE, artifacts_dir=stage_dir)
        backend.persist(result)

        data = json.loads((tmp_path / "smoke" / "plan_result.json").read_text())
        stage = data["stages"][0]
        assert stage["total_tests"] == 3
        assert stage["passed"] == 2
        assert stage["failed"] == 1
        assert stage["health_pct"] == pytest.approx(66.666, abs=0.01)
        assert data["health_pct"] == pytest.approx(66.666, abs=0.01)
        assert data["total_tests"] == 3
        assert data["passed"] == 2

    def test_health_pct_falls_back_to_binary_estimate_when_no_allure_results(
        self, tmp_path: Path
    ) -> None:
        backend = JsonBackend(tmp_path)
        result = _make_plan_result(exit_code=EngineExitCode.DOMAIN_FAILURE)
        backend.persist(result)

        data = json.loads((tmp_path / "smoke" / "plan_result.json").read_text())
        assert data["stages"][0]["total_tests"] == 0
        assert data["health_pct"] == 0.0

    def test_health_pct_counts_a_stage_that_crashed_without_results(self, tmp_path: Path) -> None:
        """A stage that crashed before running any test must not leave the cycle at the
        other stages' pass rate: 3/4 passed in one of two stages gives 37.5%, not 75%."""
        ok_dir = tmp_path / "stage" / "api"
        for name, status in [
            ("t1", "passed"),
            ("t2", "passed"),
            ("t3", "passed"),
            ("t4", "failed"),
        ]:
            _write_allure_result(ok_dir / "allure-results" / "pytest", name, status)
        ok = _make_plan_result(artifacts_dir=ok_dir).stages[0]
        crashed = StageResult(
            stage_name="flows",
            framework="behavex",
            returncode=1,
            started_at=1002.5,
            finished_at=1003.0,
            duration_s=0.5,
            log_path=None,
            artifacts_dir=tmp_path / "stage" / "flows",
            command=("behavex",),
            output_tail="OSError",
            timed_out=False,
        )
        result = PlanResult(
            plan_name="smoke",
            started_at=1000.0,
            finished_at=1003.0,
            duration_s=3.0,
            stages=(ok, crashed),
            aggregate_returncode=1,
            exit_code=EngineExitCode.DOMAIN_FAILURE,
        )

        JsonBackend(tmp_path).persist(result)

        data = json.loads((tmp_path / "smoke" / "plan_result.json").read_text())
        assert data["stages"][0]["health_pct"] == 75.0
        assert data["stages"][1]["health_pct"] is None
        assert data["health_pct"] == pytest.approx(37.5)

    def test_writes_test_time_sum_and_average(self, tmp_path: Path) -> None:
        stage_dir = tmp_path / "stage" / "api"
        _write_timed_results(stage_dir)

        JsonBackend(tmp_path).persist(_make_plan_result(artifacts_dir=stage_dir))

        data = json.loads((tmp_path / "smoke" / "plan_result.json").read_text())
        assert data["metrics_duration_ms"] == 600
        assert data["avg_case_ms"] == pytest.approx(200.0)
        assert data["stages"][0]["test_time_ms"] == 600

    def test_average_is_null_when_no_tests_ran(self, tmp_path: Path) -> None:
        JsonBackend(tmp_path).persist(_make_plan_result())

        data = json.loads((tmp_path / "smoke" / "plan_result.json").read_text())
        assert data["metrics_duration_ms"] == 0
        assert data["avg_case_ms"] is None


class TestDbBackend:
    def test_satisfies_protocol(self, tmp_path: Path) -> None:
        backend = DbBackend(tmp_path)
        assert isinstance(backend, PersistenceBackend)

    @patch("testo_core.repository.db.get_repository")
    def test_persists_successful_run(self, mock_get_repo: MagicMock, tmp_path: Path) -> None:
        mock_repo = MagicMock()
        mock_get_repo.return_value = mock_repo

        backend = DbBackend(tmp_path)
        result = _make_plan_result(target_repo=tmp_path)
        backend.persist(result)

        mock_repo.create_run.assert_called_once()
        call_kwargs = mock_repo.create_run.call_args[1]
        assert call_kwargs["status"].value == "COMPLETED"
        assert call_kwargs["metadata"]["plan"] == "smoke"
        assert call_kwargs["metadata"]["target_repo"] == str(tmp_path)
        assert call_kwargs["metadata"]["source"] == "engine"
        assert call_kwargs["metadata"]["stages"][0]["tier"] == "integration"

    @patch("testo_core.repository.db.get_repository")
    def test_health_pct_is_real_pass_rate_not_binary_returncode(
        self, mock_get_repo: MagicMock, tmp_path: Path
    ) -> None:
        mock_repo = MagicMock()
        mock_get_repo.return_value = mock_repo

        stage_dir = tmp_path / "stage" / "api"
        results_dir = stage_dir / "allure-results" / "pytest"
        _write_allure_result(results_dir, "test_one", "passed")
        _write_allure_result(results_dir, "test_two", "passed")
        _write_allure_result(results_dir, "test_three", "failed")

        backend = DbBackend(tmp_path)
        result = _make_plan_result(exit_code=EngineExitCode.DOMAIN_FAILURE, artifacts_dir=stage_dir)
        backend.persist(result)

        metadata = mock_repo.create_run.call_args[1]["metadata"]
        stage = metadata["stages"][0]
        assert stage["total_tests"] == 3
        assert stage["passed"] == 2
        assert stage["health_pct"] == pytest.approx(66.666, abs=0.01)
        assert metadata["health_pct"] == pytest.approx(66.666, abs=0.01)

    @patch("testo_core.repository.db.get_repository")
    def test_writes_test_time_sum_and_average(
        self, mock_get_repo: MagicMock, tmp_path: Path
    ) -> None:
        mock_repo = MagicMock()
        mock_get_repo.return_value = mock_repo
        stage_dir = tmp_path / "stage" / "api"
        _write_timed_results(stage_dir)

        DbBackend(tmp_path).persist(_make_plan_result(artifacts_dir=stage_dir))

        metadata = mock_repo.create_run.call_args[1]["metadata"]
        assert metadata["metrics_duration_ms"] == 600
        assert metadata["avg_case_ms"] == pytest.approx(200.0)

    @patch("testo_core.repository.db.get_repository")
    def test_persists_failed_run(self, mock_get_repo: MagicMock, tmp_path: Path) -> None:
        mock_repo = MagicMock()
        mock_get_repo.return_value = mock_repo

        backend = DbBackend(tmp_path)
        result = _make_plan_result(exit_code=EngineExitCode.DOMAIN_FAILURE)
        backend.persist(result)

        call_kwargs = mock_repo.create_run.call_args[1]
        assert call_kwargs["status"].value == "FAILED"
        assert call_kwargs["metadata"]["target_repo"] is None

    @patch("testo_core.repository.db.get_repository", side_effect=Exception("no db"))
    def test_silently_handles_db_error(self, _mock: MagicMock, tmp_path: Path) -> None:
        backend = DbBackend(tmp_path)
        result = _make_plan_result()
        run_id = backend.persist(result)
        assert run_id is None

    @patch("testo_core.repository.db.get_repository")
    def test_returns_persisted_run_id_on_success(
        self, mock_get_repo: MagicMock, tmp_path: Path
    ) -> None:
        mock_repo = MagicMock()
        fake_record = MagicMock()
        fake_record.id = "abc-123"
        mock_repo.create_run.return_value = fake_record
        mock_get_repo.return_value = mock_repo

        backend = DbBackend(tmp_path)
        result = _make_plan_result()
        run_id = backend.persist(result)

        assert run_id == "abc-123"

    @patch("testo_core.repository.db.get_repository")
    def test_sets_local_snapshot_dir_under_orchestrator_root(
        self, mock_get_repo: MagicMock
    ) -> None:
        from testo_core.paths import ORCHESTRATOR_ROOT

        mock_repo = MagicMock()
        mock_get_repo.return_value = mock_repo

        artifacts_root = ORCHESTRATOR_ROOT / "artifacts"
        backend = DbBackend(artifacts_root)
        result = _make_plan_result()
        backend.persist(result)

        metadata = mock_repo.create_run.call_args[1]["metadata"]
        assert metadata["snapshot_dir"] == "artifacts/smoke"

    @patch("testo_core.repository.db.get_repository")
    def test_snapshot_dir_none_when_outside_orchestrator_root(
        self, mock_get_repo: MagicMock, tmp_path: Path
    ) -> None:
        mock_repo = MagicMock()
        mock_get_repo.return_value = mock_repo

        backend = DbBackend(tmp_path)
        result = _make_plan_result()
        backend.persist(result)

        metadata = mock_repo.create_run.call_args[1]["metadata"]
        assert metadata["snapshot_dir"] is None

    @patch("testo_core.repository.db.get_repository")
    def test_each_run_keeps_its_own_copy_of_the_artifacts(
        self, mock_get_repo: MagicMock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Two runs of one cycle share ``artifacts/<cycle>/``; each record must not."""
        monkeypatch.setattr("testo_core.paths.ORCHESTRATOR_ROOT", tmp_path)
        history = tmp_path / "static" / "history"
        monkeypatch.setattr("testo_core.paths.STATIC_HISTORY_ROOT", history)
        mock_repo = MagicMock()
        mock_get_repo.return_value = mock_repo
        artifacts_root = tmp_path / "artifacts"
        results_dir = artifacts_root / "smoke" / "api" / "allure-results" / "pytest"
        backend = DbBackend(artifacts_root)

        for run_id, status in (("run-1", "passed"), ("run-2", "failed")):
            mock_repo.create_run.return_value = MagicMock(id=run_id)
            _write_allure_result(results_dir, "test_flaky", status)
            backend.persist(_make_plan_result())

        recorded = {
            call.args[0]: call.args[1]["snapshot_dir"]
            for call in mock_repo.merge_run_metadata.call_args_list
        }
        assert recorded == {
            "run-1": "static/history/run-1/artifacts",
            "run-2": "static/history/run-2/artifacts",
        }
        for run_id, status in (("run-1", "passed"), ("run-2", "failed")):
            copied = history / run_id / "artifacts" / "api" / "allure-results" / "pytest"
            payload = json.loads((copied / "test_flaky-result.json").read_text(encoding="utf-8"))
            assert payload["status"] == status

    @patch("testo_core.repository.db.get_repository")
    def test_snapshot_failure_keeps_the_run(self, mock_get_repo: MagicMock, tmp_path: Path) -> None:
        mock_repo = MagicMock()
        mock_repo.create_run.return_value = MagicMock(id="run-1")
        mock_repo.merge_run_metadata.side_effect = RuntimeError("db went away")
        mock_get_repo.return_value = mock_repo
        (tmp_path / "smoke").mkdir()

        assert DbBackend(tmp_path).persist(_make_plan_result()) == "run-1"


class TestCompositeBackend:
    def test_fans_out_to_all_backends(self, tmp_path: Path) -> None:
        with patch("testo_core.repository.db.get_repository") as mock_get_repo:
            mock_repo = MagicMock()
            mock_get_repo.return_value = mock_repo

            backend = composite_backend(artifacts_root=tmp_path, db=True)
            result = _make_plan_result()
            backend.persist(result)

            assert (tmp_path / "smoke" / "plan_result.json").exists()
            mock_repo.create_run.assert_called_once()

    def test_json_only_when_db_disabled(self, tmp_path: Path) -> None:
        backend = composite_backend(artifacts_root=tmp_path, db=False)
        result = _make_plan_result()
        backend.persist(result)

        assert (tmp_path / "smoke" / "plan_result.json").exists()

    def test_continues_on_backend_failure(self, tmp_path: Path) -> None:
        with patch("testo_core.repository.db.get_repository", side_effect=RuntimeError):
            backend = composite_backend(artifacts_root=tmp_path, db=True)
            result = _make_plan_result()
            backend.persist(result)
            assert (tmp_path / "smoke" / "plan_result.json").exists()

    def test_returns_db_backend_run_id(self, tmp_path: Path) -> None:
        with patch("testo_core.repository.db.get_repository") as mock_get_repo:
            mock_repo = MagicMock()
            fake_record = MagicMock()
            fake_record.id = "run-xyz"
            mock_repo.create_run.return_value = fake_record
            mock_get_repo.return_value = mock_repo

            backend = composite_backend(artifacts_root=tmp_path, db=True)
            result = _make_plan_result()
            run_id = backend.persist(result)

            assert run_id == "run-xyz"

    def test_returns_none_when_db_disabled(self, tmp_path: Path) -> None:
        backend = composite_backend(artifacts_root=tmp_path, db=False)
        result = _make_plan_result()
        run_id = backend.persist(result)
        assert run_id is None
