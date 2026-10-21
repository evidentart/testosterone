"""The non-interactive starter works for an ordinary pytest project."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from testo_core.cli.app import app
from testo_core.config.loader import discover_and_load

pytestmark = [pytest.mark.unit, pytest.mark.tier_fast]


def test_config_init_writes_loadable_pytest_starter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cli_runner: CliRunner
) -> None:
    monkeypatch.chdir(tmp_path)

    result = cli_runner.invoke(app, ["config", "init"])

    assert result.exit_code == 0, result.output
    cfg = discover_and_load(cwd=tmp_path)
    stage = cfg.cycles["smoke-test"].stages[0]
    assert stage.framework == "pytest"
    assert stage.target_repo == tmp_path
    assert stage.args == ("-q", "tests")
    assert list(cfg.cycles) == ["smoke-test"]
    assert len(cfg.cycles["smoke-test"].stages) == 1


def test_config_init_validates_with_only_pytest_available(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cli_runner: CliRunner
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "testo_core.cli.commands.config.shutil.which",
        lambda exe: "/available/pytest" if exe == "pytest" else None,
    )
    result = cli_runner.invoke(app, ["config", "init"])
    assert result.exit_code == 0, result.output

    result = cli_runner.invoke(app, ["config", "validate"])

    assert result.exit_code == 0, result.output
