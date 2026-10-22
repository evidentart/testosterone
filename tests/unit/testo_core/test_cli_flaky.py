"""``testo flaky``: rendering, JSON output and the ``--fail-on-flaky`` gate."""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from testo_core.cli.app import app
from testo_core.services.flaky_service import FlakyReport, FlakyTest

_FLAKY = FlakyTest(
    key="k",
    name="test_flaky_route",
    group="tests.api",
    runs=3,
    passed=2,
    failed=1,
    flips=2,
    flip_rate=1.0,
    last_status="passed",
    history=("passed", "failed", "passed"),
)


def _patch(monkeypatch: pytest.MonkeyPatch, *, runs: int, flaky: tuple[FlakyTest, ...]) -> None:
    def _fake(*, cycle: str, window: int) -> FlakyReport:
        return FlakyReport(
            cycle=cycle, window=window, runs_analyzed=runs, tests_analyzed=5, flaky=flaky
        )

    monkeypatch.setattr("testo_core.services.flaky_service.find_flaky_tests", _fake)


def test_lists_flaky_tests(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch(monkeypatch, runs=3, flaky=(_FLAKY,))
    result = CliRunner().invoke(app, ["flaky", "--cycle", "fake-api"])
    assert result.exit_code == 0, result.stdout
    assert "test_flaky_route" in result.stdout
    assert "5 tests across the last 3 runs" in result.stdout


def test_fail_on_flaky_exits_1(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch(monkeypatch, runs=3, flaky=(_FLAKY,))
    assert CliRunner().invoke(app, ["flaky", "--cycle", "x", "--fail-on-flaky"]).exit_code == 1
    _patch(monkeypatch, runs=3, flaky=())
    assert CliRunner().invoke(app, ["flaky", "--cycle", "x", "--fail-on-flaky"]).exit_code == 0


def test_json_output(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch(monkeypatch, runs=3, flaky=(_FLAKY,))
    result = CliRunner().invoke(app, ["flaky", "--cycle", "x", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["flaky"][0]["history"] == ["passed", "failed", "passed"]


def test_too_few_runs_is_invalid_input(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch(monkeypatch, runs=1, flaky=())
    result = CliRunner().invoke(app, ["flaky", "--cycle", "x"])
    assert result.exit_code == 2
    assert "at least two" in result.stdout


def test_quarantined_flaky_tests_are_marked_and_dont_fail_the_gate(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    cfg = tmp_path / "testosterone.yaml"
    cfg.write_text(
        "version: 1\ncycles:\n  x:\n    quarantine: [test_flaky_*]\n"
        "    stages:\n      - {name: unit, framework: pytest}\n",
        encoding="utf-8",
    )
    other = FlakyTest(**{**_FLAKY.__dict__, "key": "k2", "name": "test_other"})
    _patch(monkeypatch, runs=3, flaky=(_FLAKY,))
    args = ["flaky", "--cycle", "x", "--config", str(cfg)]
    assert CliRunner().invoke(app, [*args, "--fail-on-flaky"]).exit_code == 0
    payload = json.loads(CliRunner().invoke(app, [*args, "--json"]).stdout)
    assert payload["flaky"][0]["quarantined"] is True

    _patch(monkeypatch, runs=3, flaky=(_FLAKY, other))
    result = CliRunner().invoke(app, args)
    assert "yes" in result.stdout
    assert '- test: "test_other"' in result.stdout
    assert '- test: "test_flaky_route"' not in result.stdout
    assert CliRunner().invoke(app, [*args, "--fail-on-flaky"]).exit_code == 1


def test_bad_config_is_invalid_input(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    _patch(monkeypatch, runs=3, flaky=(_FLAKY,))
    missing = tmp_path / "nope.yaml"
    result = CliRunner().invoke(app, ["flaky", "--cycle", "x", "--config", str(missing)])
    assert result.exit_code == 2


def test_new_keeps_only_tests_the_latest_run_made_flaky(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch(monkeypatch, runs=3, flaky=(_FLAKY,))
    monkeypatch.setattr(
        "testo_core.services.flaky_service.newly_flaky_tests", lambda *, cycle, window: ()
    )
    result = CliRunner().invoke(app, ["flaky", "--cycle", "x", "--new", "--json"])
    assert result.exit_code == 0
    assert json.loads(result.stdout)["flaky"] == []
