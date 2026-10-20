"""Config loader tests for top-level ``reporters:``."""

from __future__ import annotations

from pathlib import Path

import pytest

from testo_core.config.errors import ConfigValidationError
from testo_core.config.loader import load_config


def _minimal_cycles_yaml(*extra: str) -> str:
    base = """
version: 1
defaults:
  target_repo: .
  artifacts_root: artifacts
cycles:
  smoke:
    stages:
      - name: s
        equipment: pytest
        args: ["--version"]
"""
    return base + "\n".join(extra)


def test_parse_reporters_valid(tmp_path: Path) -> None:
    cfg_path = tmp_path / "testosterone.yaml"
    cfg_path.write_text(
        _minimal_cycles_yaml(
            """
reporters:
  - type: extent
    output_dir: ./reports/extent
  - type: testbeats
    slack_webhook: ${env:SLACK_WEBHOOK}
"""
        ),
        encoding="utf-8",
    )
    cfg = load_config(cfg_path)
    assert len(cfg.reporters) == 2
    assert cfg.reporters[0].type == "extent"
    opts0 = dict(cfg.reporters[0].options)
    assert opts0["output_dir"].endswith("reports/extent")
    assert cfg.reporters[1].type == "testbeats"
    assert dict(cfg.reporters[1].options)["slack_webhook"] == "${env:SLACK_WEBHOOK}"


def test_parse_reporters_empty_omitted(tmp_path: Path) -> None:
    cfg_path = tmp_path / "testosterone.yaml"
    cfg_path.write_text(_minimal_cycles_yaml(), encoding="utf-8")
    cfg = load_config(cfg_path)
    assert cfg.reporters == ()


def test_parse_reporters_unknown_type(tmp_path: Path) -> None:
    cfg_path = tmp_path / "testosterone.yaml"
    cfg_path.write_text(
        _minimal_cycles_yaml(
            """
reporters:
  - type: unknown
"""
        ),
        encoding="utf-8",
    )
    with pytest.raises(ConfigValidationError, match="unsupported type"):
        load_config(cfg_path)


def test_parse_reporters_name_alias(tmp_path: Path) -> None:
    cfg_path = tmp_path / "testosterone.yaml"
    cfg_path.write_text(
        _minimal_cycles_yaml(
            """
reporters:
  - name: allure
"""
        ),
        encoding="utf-8",
    )
    cfg = load_config(cfg_path)
    assert cfg.reporters[0].type == "allure"
