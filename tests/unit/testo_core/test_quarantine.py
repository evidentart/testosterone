"""Quarantine: config parsing, rule matching, and the stage gate end to end."""

from __future__ import annotations

import json
import sys
import textwrap
from pathlib import Path

import pytest

from testo_core.config.errors import ConfigValidationError
from testo_core.config.loader import load_config
from testo_core.config.schema import Plan, QuarantineRule, Stage
from testo_core.engine.executor import run_stage
from testo_core.engine.exit_codes import EngineExitCode
from testo_core.engine.orchestrator import run_plan
from testo_core.engine.quarantine import evaluate, matching_rule

pytestmark = [pytest.mark.unit, pytest.mark.tier_fast]


def _config(tmp_path: Path, body: str) -> Path:
    cfg = tmp_path / "testosterone.yaml"
    cfg.write_text(textwrap.dedent(body), encoding="utf-8")
    return cfg


# --- config ----------------------------------------------------------------------


def test_top_level_and_cycle_rules_are_merged(tmp_path: Path) -> None:
    cfg = _config(
        tmp_path,
        """\
        version: 1
        quarantine:
          - test_shared_flake
        cycles:
          app:
            quarantine:
              - test: "test_checkout*"
                reason: races the payment mock
                owner: "@taltal"
            stages:
              - {name: unit, framework: pytest}
          other:
            stages:
              - {name: unit, framework: pytest}
        """,
    )
    cycles = load_config(cfg).cycles
    assert cycles["app"].quarantine == (
        QuarantineRule(test="test_shared_flake"),
        QuarantineRule(test="test_checkout*", reason="races the payment mock", owner="@taltal"),
    )
    assert cycles["other"].quarantine == (QuarantineRule(test="test_shared_flake"),)


@pytest.mark.parametrize(
    ("quarantine_yaml", "match"),
    [
        ("quarantine: test_x", "must be a list"),
        ("quarantine: [{reason: no test}]", "'test' must be a non-empty string"),
        ("quarantine: ['  ']", "'test' must be a non-empty string"),
        ("quarantine: [{test: t, until: tomorrow}]", "unknown key"),
        ("quarantine: [{test: t, owner: 3}]", "'owner' must be a string"),
        ("quarantine: [[t]]", "must be a test name or a mapping"),
    ],
)
def test_bad_quarantine_entries_are_rejected(
    tmp_path: Path, quarantine_yaml: str, match: str
) -> None:
    cfg = _config(
        tmp_path,
        f"version: 1\n{quarantine_yaml}\ncycles:\n  app:\n    stages:\n"
        "      - {name: unit, framework: pytest}\n",
    )
    with pytest.raises(ConfigValidationError, match=match):
        load_config(cfg)


# --- matching ----------------------------------------------------------------------


def test_rules_match_name_or_full_name_as_globs() -> None:
    rules = (QuarantineRule(test="test_pay*"), QuarantineRule(test="tests.api#*"))
    assert matching_rule(rules, name="test_payout[1]") == rules[0]
    assert matching_rule(rules, name="test_ok", full_name="tests.api#test_ok") == rules[1]
    assert matching_rule(rules, name="test_other", full_name="tests.web#test_other") is None


def _write_result(results_dir: Path, name: str, status: str, full_name: str = "") -> None:
    results_dir.mkdir(parents=True, exist_ok=True)
    payload = {"name": name, "fullName": full_name or f"mod#{name}", "status": status}
    (results_dir / f"{name}-result.json").write_text(json.dumps(payload), encoding="utf-8")


def test_evaluate_splits_failures(tmp_path: Path) -> None:
    _write_result(tmp_path, "test_flaky", "failed")
    _write_result(tmp_path, "test_broken_flaky", "broken")
    _write_result(tmp_path, "test_real_bug", "failed")
    _write_result(tmp_path, "test_fine", "passed")
    verdict = evaluate((QuarantineRule(test="*flaky"),), tmp_path)
    assert verdict.quarantined == ("test_broken_flaky", "test_flaky")
    assert verdict.unquarantined == ("test_real_bug",)
    assert not verdict.waives_stage


def test_no_failed_results_never_waive(tmp_path: Path) -> None:
    _write_result(tmp_path, "test_fine", "passed")
    assert not evaluate((QuarantineRule(test="*"),), tmp_path).waives_stage


# --- the gate, through run_stage -----------------------------------------------------

_JUNIT = """\
<testsuite name="api" tests="3">
  <testcase classname="api" name="test_ok"/>
  <testcase classname="api" name="test_flaky_route"><failure message="boom"/></testcase>
  {extra}
</testsuite>
"""


def _stage(tmp_path: Path, *, exit_code: int, extra_case: str = "") -> Stage:
    """A command stage that writes a JUnit report with one failure and exits ``exit_code``."""
    repo = tmp_path / "repo"
    repo.mkdir(exist_ok=True)
    script = repo / "fake_runner.py"
    script.write_text(
        "import pathlib, sys\n"
        f"pathlib.Path('junit.xml').write_text({_JUNIT.format(extra=extra_case)!r})\n"
        f"sys.exit({exit_code})\n",
        encoding="utf-8",
    )
    return Stage(
        name="api",
        framework="command",
        target_repo=repo,
        args=(sys.executable, str(script)),
        junit_xml=("junit.xml",),
    )


def test_quarantined_failure_passes_the_stage_and_is_recorded(tmp_path: Path) -> None:
    result = run_stage(
        _stage(tmp_path, exit_code=1),
        plan_name="app",
        artifacts_root=tmp_path / "a",
        quarantine=(QuarantineRule(test="test_flaky_*"),),
    )
    assert result.returncode == 0
    assert result.waived_returncode == 1
    assert result.quarantined == ("test_flaky_route",)
    log = (tmp_path / "a" / "app" / "api" / "run.log").read_text()
    assert "failed but quarantined: test_flaky_route" in log
    assert "the stage passes" in log
    # The failure itself is still in the results every report reads.
    results = tmp_path / "a" / "app" / "api" / "allure-results" / "command"
    statuses = {
        json.loads(p.read_text())["name"]: json.loads(p.read_text())["status"]
        for p in results.glob("*-result.json")
    }
    assert statuses["test_flaky_route"] == "failed"


def test_an_unquarantined_failure_still_fails_the_stage(tmp_path: Path) -> None:
    extra = '<testcase classname="api" name="test_real_bug"><failure message="x"/></testcase>'
    result = run_stage(
        _stage(tmp_path, exit_code=1, extra_case=extra),
        plan_name="app",
        artifacts_root=tmp_path / "a",
        quarantine=(QuarantineRule(test="test_flaky_*"),),
    )
    assert result.returncode == 1
    assert result.waived_returncode is None
    assert result.quarantined == ("test_flaky_route",)
    assert (
        "1 failure(s) not quarantined" in (tmp_path / "a" / "app" / "api" / "run.log").read_text()
    )


def test_only_returncode_1_can_be_waived(tmp_path: Path) -> None:
    result = run_stage(
        _stage(tmp_path, exit_code=2),
        plan_name="app",
        artifacts_root=tmp_path / "a",
        quarantine=(QuarantineRule(test="*"),),
    )
    assert result.returncode == 2
    assert result.quarantined == ()


def test_plan_exit_code_honors_the_quarantine(tmp_path: Path) -> None:
    class _Quiet:
        wants_streaming = False

        def handle(self, event: object) -> None:
            pass

    plan = Plan(
        name="app",
        description=None,
        stages=(_stage(tmp_path, exit_code=1),),
        quarantine=(QuarantineRule(test="test_flaky_route"),),
    )
    result = run_plan(plan, renderer=_Quiet(), artifacts_root=tmp_path / "a", persist=False)
    assert result.exit_code == EngineExitCode.SUCCESS
    events = [
        json.loads(line)
        for line in (tmp_path / "a" / "app" / "events.ndjson").read_text().splitlines()
    ]
    finished = next(e for e in events if e["event"] == "stage_finished")
    assert finished["quarantined"] == ["test_flaky_route"]
    assert finished["waived_returncode"] == 1


def test_quarantine_applies_to_recorded_junit_stages(tmp_path: Path) -> None:
    # ``equipment: junit`` runs no process, so the gate reads the recorded results.
    from testo_core.services.cycle_run import junit_ingest_plan

    (tmp_path / "junit.xml").write_text(
        '<testsuite name="pay"><testcase classname="pay" name="test_flaky_refund">'
        '<failure message="boom">trace</failure></testcase></testsuite>',
        encoding="utf-8",
    )
    stage = junit_ingest_plan(cycle="web", reports=["junit.xml"], target_repo=tmp_path).stages[0]
    result = run_stage(
        stage,
        plan_name="web",
        artifacts_root=tmp_path / "out",
        quarantine=(QuarantineRule(test="test_flaky_*"),),
    )
    assert result.returncode == 0
    assert result.waived_returncode == 1
    assert result.quarantined == ("test_flaky_refund",)
