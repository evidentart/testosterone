"""``junit`` equipment and ``testo ingest``: record JUnit XML another step wrote,
through the same engine as ``testo run``."""

from __future__ import annotations

import dataclasses
import os
import textwrap
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from testo_core.cli.app import app
from testo_core.cli.runner import matching_reports, report_patterns
from testo_core.config.errors import ConfigError, ConfigValidationError
from testo_core.config.loader import load_config
from testo_core.engine.executor import run_stage
from testo_core.engine.orchestrator import run_plan
from testo_core.frameworks.base import get_adapter
from testo_core.persistence.db_backend import DbBackend
from testo_core.services.cycle_run import junit_ingest_plan
from tests.fixtures.engine import NoopRenderer

pytestmark = [pytest.mark.unit, pytest.mark.tier_fast]

PASSING = textwrap.dedent(
    """\
    <?xml version="1.0"?>
    <testsuite name="cart" tests="2">
      <testcase classname="cart" name="adds item" time="0.25"/>
      <testcase classname="cart" name="skips" time="0"><skipped/></testcase>
    </testsuite>
    """
)
FAILING = textwrap.dedent(
    """\
    <?xml version="1.0"?>
    <testsuite name="pay" tests="2">
      <testcase classname="pay" name="charges" time="0.5"/>
      <testcase classname="pay" name="refunds" time="1.25"><failure message="boom">trace</failure></testcase>
    </testsuite>
    """
)


def _write(path: Path, body: str, *, age_s: float = 0) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    if age_s:
        old = time.time() - age_s
        os.utime(path, (old, old))
    return path


# --- config ----------------------------------------------------------------------


def test_config_accepts_junit_stage(tmp_path: Path) -> None:
    cfg_path = tmp_path / "testosterone.yaml"
    cfg_path.write_text(
        "version: 1\ncycles:\n  web:\n    stages:\n"
        "      - name: jest\n        equipment: junit\n        junit_xml: reports/*.xml\n",
        encoding="utf-8",
    )
    stage = load_config(cfg_path).cycles["web"].stages[0]
    assert stage.framework == "junit"
    assert stage.junit_xml == ("reports/*.xml",)
    assert stage.tier == "unit"


def test_config_rejects_junit_stage_without_reports(tmp_path: Path) -> None:
    cfg_path = tmp_path / "testosterone.yaml"
    cfg_path.write_text(
        "version: 1\ncycles:\n  web:\n    stages:\n      - name: jest\n        equipment: junit\n",
        encoding="utf-8",
    )
    with pytest.raises(ConfigValidationError, match="needs 'junit_xml'"):
        load_config(cfg_path)


def test_adapter_runs_no_process() -> None:
    adapter = get_adapter("junit")
    assert adapter.runs_process is False  # type: ignore[attr-defined]
    assert adapter.results_subdir() == "junit"


# --- junit_ingest_plan ----------------------------------------------------------------


def test_ingest_plan_is_one_junit_stage(tmp_path: Path) -> None:
    plan = junit_ingest_plan(cycle="web-unit", reports=["r/*.xml"], target_repo=tmp_path)
    assert plan.name == "web-unit"
    (stage,) = plan.stages
    assert (stage.name, stage.framework, stage.junit_xml) == ("junit", "junit", ("r/*.xml",))
    assert stage.target_repo == tmp_path.resolve()


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"cycle": "../etc"}, "cycle name"),
        ({"cycle": "a/b"}, "cycle name"),
        ({"stage_name": ""}, "stage name"),
        ({"reports": ["/etc/passwd"]}, "must be relative"),
        ({"reports": ["../x.xml"]}, "must be relative"),
        ({"reports": [" "]}, "no JUnit XML"),
        ({"tier": "smoke"}, "unsupported tier"),
    ],
)
def test_ingest_plan_rejects_unsafe_input(tmp_path: Path, kwargs: dict, message: str) -> None:
    args: dict = {"cycle": "web", "reports": ["r.xml"], "target_repo": tmp_path, **kwargs}
    with pytest.raises(ConfigValidationError, match=message):
        junit_ingest_plan(**args)


# --- executor ---------------------------------------------------------------------


def _stage(tmp_path: Path, *patterns: str):  # noqa: ANN202
    return junit_ingest_plan(cycle="web", reports=list(patterns), target_repo=tmp_path).stages[0]


def test_passing_reports_give_returncode_0_even_when_older_than_the_stage(tmp_path: Path) -> None:
    _write(tmp_path / "reports" / "a.xml", PASSING, age_s=3600)
    result = run_stage(
        _stage(tmp_path, "reports/*.xml"), plan_name="web", artifacts_root=tmp_path / "artifacts"
    )
    assert result.returncode == 0
    assert result.error is None
    assert result.command == ()
    assert result.duration_s == pytest.approx(0.25)
    results = list((result.artifacts_dir / "allure-results" / "junit").glob("*-result.json"))
    assert len(results) == 2
    assert "recorded 2 test(s), 0 failed" in result.log_path.read_text()  # type: ignore[union-attr]


def test_a_failed_case_gives_returncode_1(tmp_path: Path) -> None:
    _write(tmp_path / "a.xml", PASSING)
    _write(tmp_path / "b.xml", FAILING)
    result = run_stage(_stage(tmp_path, "*.xml"), plan_name="web", artifacts_root=tmp_path / "out")
    assert result.returncode == 1
    assert result.duration_s == pytest.approx(2.0)


def test_no_matching_report_fails_loudly(tmp_path: Path) -> None:
    result = run_stage(
        _stage(tmp_path, "missing/*.xml"), plan_name="web", artifacts_root=tmp_path / "out"
    )
    assert result.returncode == 1
    assert result.error is not None and "no JUnit XML matched" in result.error


def test_plan_duration_is_the_recorded_test_time(tmp_path: Path) -> None:
    _write(tmp_path / "b.xml", FAILING)
    plan = junit_ingest_plan(cycle="web", reports=["b.xml"], target_repo=tmp_path)
    result = run_plan(plan, renderer=NoopRenderer(), artifacts_root=tmp_path / "out", persist=False)
    assert int(result.exit_code) == 1
    assert result.duration_s == pytest.approx(1.75)


def test_run_metadata_reaches_the_run_record(tmp_path: Path) -> None:
    _write(tmp_path / "a.xml", PASSING)
    plan = junit_ingest_plan(cycle="web", reports=["a.xml"], target_repo=tmp_path)
    result = run_plan(
        plan,
        renderer=NoopRenderer(),
        artifacts_root=tmp_path / "out",
        persist=False,
        run_metadata={"ci_provider": "github", "ci_commit_sha": "abc123"},
    )
    assert result.extra["run_metadata"] == {"ci_provider": "github", "ci_commit_sha": "abc123"}

    repo = MagicMock()
    with (
        patch("testo_core.repository.db.get_repository", return_value=repo),
        patch.dict(os.environ, {"GITHUB_ACTIONS": "", "CI": ""}),
    ):
        DbBackend(tmp_path / "out").persist(dataclasses.replace(result))
    metadata = repo.create_run.call_args[1]["metadata"]
    assert metadata["ci_provider"] == "github"
    assert metadata["ci_commit_sha"] == "abc123"


# --- CLI helpers --------------------------------------------------------------------


def test_report_patterns_relativizes_absolute_paths_inside_repo(tmp_path: Path) -> None:
    inside = _write(tmp_path / "r" / "a.xml", PASSING)
    assert report_patterns([str(inside), "r/*.xml"], repo=tmp_path.resolve()) == (
        "r/a.xml",
        "r/*.xml",
    )
    with pytest.raises(ConfigError, match="outside --repo"):
        report_patterns(["/elsewhere/a.xml"], repo=tmp_path.resolve())


def test_matching_reports_deduplicates(tmp_path: Path) -> None:
    a = _write(tmp_path / "r" / "a.xml", PASSING)
    assert matching_reports(("r/*.xml", "r/a.xml"), repo=tmp_path.resolve()) == [a.resolve()]


# --- testo ingest ------------------------------------------------------------------


@pytest.fixture
def in_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_cli_ingest_exit_code_follows_the_results(in_tmp: Path) -> None:
    _write(in_tmp / "reports" / "ok.xml", PASSING)
    _write(in_tmp / "reports" / "bad.xml", FAILING)
    runner = CliRunner()
    ok = runner.invoke(app, ["ingest", "reports/ok.xml", "--cycle", "web", "--no-persist", "--ci"])
    assert ok.exit_code == 0, ok.output
    assert '"framework":"junit"' in ok.output
    bad = runner.invoke(app, ["ingest", "reports/*.xml", "--cycle", "web", "--no-persist", "--ci"])
    assert bad.exit_code == 1, bad.output


def test_cli_ingest_without_matches_is_invalid_input(in_tmp: Path) -> None:
    result = CliRunner().invoke(app, ["ingest", "nope/*.xml", "--cycle", "web", "--no-persist"])
    assert result.exit_code == 2
    assert "no JUnit XML file matches" in result.output


def test_cli_ingest_rejects_unsafe_cycle_name(in_tmp: Path) -> None:
    _write(in_tmp / "ok.xml", PASSING)
    result = CliRunner().invoke(app, ["ingest", "ok.xml", "--cycle", "../x", "--no-persist"])
    assert result.exit_code == 2
