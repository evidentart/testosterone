"""The ``testosterone.yaml`` JSON Schema agrees with the loader and is up to date."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

import jsonschema
import pytest
import yaml

from testo_core.config.json_schema import build_json_schema
from testo_core.config.loader import load_config

REPO_ROOT = Path(__file__).resolve().parents[3]

pytestmark = pytest.mark.contract


def _validator() -> jsonschema.Draft7Validator:
    schema = build_json_schema()
    jsonschema.Draft7Validator.check_schema(schema)
    return jsonschema.Draft7Validator(schema)


def _errors(doc: Any) -> list[str]:
    return [e.message for e in _validator().iter_errors(doc)]


def test_committed_schema_is_up_to_date() -> None:
    spec = importlib.util.spec_from_file_location(
        "export_config_schema", REPO_ROOT / "scripts" / "export_config_schema.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.main(["--check"]) == 0
    committed = json.loads(module.SCHEMA_PATH.read_text(encoding="utf-8"))
    assert committed == build_json_schema()


@pytest.mark.parametrize(
    "path",
    [
        "testosterone.yaml",
        "examples/getting-started/testosterone.yaml",
        "examples/plugin/testosterone.yaml",
    ],
)
def test_repo_configs_match_schema(path: str) -> None:
    doc = yaml.safe_load((REPO_ROOT / path).read_text(encoding="utf-8"))
    assert _errors(doc) == []


def test_starter_templates_match_schema_and_loader(tmp_path: Path) -> None:
    from testo_core.cli.commands.config import _STARTER_YAML

    assert _errors(yaml.safe_load(_STARTER_YAML)) == []
    cfg_path = tmp_path / "testosterone.yaml"
    cfg_path.write_text(_STARTER_YAML, encoding="utf-8")
    assert load_config(cfg_path).cycles


def test_full_config_is_valid() -> None:
    doc = {
        "version": 1,
        "database": {"url": "sqlite:////tmp/t.db"},
        "defaults": {"target_repo": ".", "timeout_s": None, "workers": 2, "extra_env": {"A": 1}},
        "reporters": [{"type": "allure"}, {"type": "slack", "when": "change"}],
        "quarantine": ["test_upload_retries"],
        "cycles": {
            "pr": {
                "description": "PR gate",
                "quarantine": [{"test": "test_flaky_*", "reason": "races", "owner": "@taltal"}],
                "trigger": {"paths": ["src/**"], "since_ref": "origin/main"},
                "stages": [
                    {"name": "unit", "equipment": "pytest", "args": "-q tests", "tier": "unit"},
                    {
                        "name": "jest",
                        "equipment": "command",
                        "args": ["npx", "jest"],
                        "junit_xml": ["reports/*.xml"],
                        "if": "env.CI",
                    },
                    {"name": "legacy", "framework": "behave", "args": ["features/smoke.feature"]},
                    {"name": "go", "equipment": "junit", "junit_xml": ["reports/go-*.xml"]},
                ],
            }
        },
    }
    assert _errors(doc) == []


@pytest.mark.parametrize(
    ("doc", "fragment"),
    [
        ({"version": 1}, "'cycles' is a required property"),
        (
            {"cycles": {"c": {"stages": [{"name": "s", "equipment": "pytest", "worker": 2}]}}},
            "'worker' was unexpected",
        ),
        (
            {"cycles": {"c": {"stages": [{"name": "s", "equipment": "pytest", "tier": "smoke"}]}}},
            "'smoke' is not one of",
        ),
        (
            {"cycles": {"c": {"stages": [{"name": "s"}]}}},
            "is not valid under any of the given schemas",
        ),
        ({"cycles": {"c": {"stages": []}}}, "should be non-empty"),
        (
            {"cycles": {"all": {"stages": [{"name": "s", "equipment": "pytest"}]}}},
            "should not be valid",
        ),
        (
            {"cycles": {"c": {"stages": [{"name": "../up", "equipment": "pytest"}]}}},
            "does not match",
        ),
        ({"cycels": {}}, "'cycels' was unexpected"),
        (
            {"quarantine": [{"test": "t", "ownr": "@x"}], "cycles": {}},
            "is not valid under any of the given schemas",
        ),
    ],
)
def test_invalid_configs_are_flagged(doc: dict[str, Any], fragment: str) -> None:
    errors = _errors(doc)
    assert any(fragment in e for e in errors), errors
