from __future__ import annotations

import json
from pathlib import Path

import pytest

from testo_core.services.ai.integration_settings import (
    AI_SETTINGS_PATH_ENV,
    AiIntegrationSettings,
    FileBackedAiSettingsStore,
    default_ai_settings_path,
)


def test_settings_survive_a_new_store_but_the_runtime_key_does_not(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "ai_settings.json"
    store = FileBackedAiSettingsStore(path)
    store.update(
        enabled=True,
        provider="anthropic",
        model="claude-haiku-4-5",
        api_key_source="runtime_input",
        runtime_api_key="sk-secret",
    )

    assert "sk-secret" not in path.read_text(encoding="utf-8")
    assert "runtime_api_key" not in json.loads(path.read_text(encoding="utf-8"))

    reloaded = FileBackedAiSettingsStore(path).get()
    assert reloaded.enabled is True
    assert reloaded.provider == "anthropic"
    assert reloaded.model == "claude-haiku-4-5"
    assert reloaded.api_key_source == "runtime_input"
    assert reloaded.runtime_api_key is None


@pytest.mark.parametrize(
    "content",
    ["{not json", "[]", json.dumps({"timeout_s": -1}), json.dumps({"provider": "nope"})],
)
def test_bad_settings_file_falls_back_to_defaults(
    tmp_path: Path, content: str, caplog: pytest.LogCaptureFixture
) -> None:
    path = tmp_path / "ai_settings.json"
    path.write_text(content, encoding="utf-8")

    with caplog.at_level("WARNING"):
        settings = FileBackedAiSettingsStore(path).get()

    assert settings == AiIntegrationSettings()
    assert str(path) in caplog.text


def test_unwritable_path_keeps_settings_in_memory(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    blocker = tmp_path / "file"
    blocker.write_text("x", encoding="utf-8")
    store = FileBackedAiSettingsStore(blocker / "ai_settings.json")

    with caplog.at_level("WARNING"):
        store.update(enabled=True)

    assert store.get().enabled is True
    assert "lost on restart" in caplog.text


def test_default_path_and_opt_out(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv(AI_SETTINGS_PATH_ENV, raising=False)
    assert default_ai_settings_path() == Path("artifacts") / "ai_settings.json"

    monkeypatch.setenv(AI_SETTINGS_PATH_ENV, "")
    assert default_ai_settings_path() is None

    monkeypatch.setenv(AI_SETTINGS_PATH_ENV, str(tmp_path / "x.json"))
    assert default_ai_settings_path() == tmp_path / "x.json"
