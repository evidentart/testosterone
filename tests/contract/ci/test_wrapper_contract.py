from __future__ import annotations

import importlib.util
from pathlib import Path

import yaml


def _load_wrapper_module():
    script = Path("integrations/github-action/run_testo_action.py").resolve()
    spec = importlib.util.spec_from_file_location("run_testo_action_contract", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_action_contract_has_required_inputs_outputs() -> None:
    payload = yaml.safe_load(
        Path("integrations/github-action/action.yml").read_text(encoding="utf-8")
    )
    assert set(payload["inputs"].keys()) == {
        "config-path",
        "cycle",
        "ci-mode",
        "persist",
        "python-version",
        "package",
        "job-summary",
        "comment-on-pr",
        "github-token",
    }
    assert set(payload["outputs"].keys()) == {"exit_code", "summary_json", "summary_path", "status"}


def test_wrapper_uses_testo_run_ci_command_shape() -> None:
    module = _load_wrapper_module()
    cmd = module.build_command(config_path="config.yml", cycle="", ci_mode=True, persist=True)
    assert cmd[:2] == ["testo", "run"]
    assert "--ci" in cmd


def test_github_fixture_is_one_line_consumer() -> None:
    workflow = Path("tests/fixtures/ci/github_workflow_minimal.yml").read_text(encoding="utf-8")
    assert "uses: taltal-beep/testosterone/integrations/github-action@v1" in workflow
