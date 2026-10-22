from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, fields, replace
from pathlib import Path
from threading import Lock
from typing import Any

from testo_core.paths import default_artifacts_root

from .config import AiProviderConfig, ApiKeySource
from .provider_base import AiProviderName

logger = logging.getLogger(__name__)

# Where the API keeps AI settings between restarts. Set it to an empty string to keep
# them in memory only.
AI_SETTINGS_PATH_ENV = "TESTO_AI_SETTINGS_PATH"

# Never written to disk: a key typed into the UI lives only as long as the API process.
_UNPERSISTED_FIELDS = frozenset({"runtime_api_key"})


@dataclass(frozen=True)
class AiIntegrationSettings:
    enabled: bool = False
    provider: AiProviderName = "openai"
    model: str = "gpt-4o-mini"
    api_key_source: ApiKeySource = "env"
    api_key_env_var: str | None = None
    timeout_s: float = 8.0
    retry_count: int = 1
    max_input_chars: int = 16_000
    max_output_tokens: int = 300
    base_url: str | None = None
    runtime_api_key: str | None = None

    def to_provider_config(self) -> AiProviderConfig:
        return AiProviderConfig(
            enabled=self.enabled,
            provider=self.provider,
            model=self.model,
            api_key_source=self.api_key_source,
            api_key_env_var=self.api_key_env_var,
            timeout_s=self.timeout_s,
            retry_count=self.retry_count,
            max_input_chars=self.max_input_chars,
            max_output_tokens=self.max_output_tokens,
            base_url=self.base_url,
        )

    def to_public_status(self) -> dict[str, object]:
        key_present = bool(self.runtime_api_key) if self.api_key_source == "runtime_input" else None
        return {
            "enabled": self.enabled,
            "configured": key_present if key_present is not None else False,
            "provider": self.provider,
            "model": self.model,
            "api_key_source": self.api_key_source,
            "api_key_env_var": self.api_key_env_var,
            "key_present": key_present,
            "timeout_s": self.timeout_s,
            "retry_count": self.retry_count,
            "max_input_chars": self.max_input_chars,
            "max_output_tokens": self.max_output_tokens,
            "base_url": self.base_url,
        }


class InMemoryAiSettingsStore:
    def __init__(self) -> None:
        self._settings = AiIntegrationSettings()
        self._lock = Lock()

    def get(self) -> AiIntegrationSettings:
        with self._lock:
            return self._settings

    def update(self, **kwargs: Any) -> AiIntegrationSettings:
        with self._lock:
            self._settings = replace(self._settings, **kwargs)
            return self._settings


def default_ai_settings_path() -> Path | None:
    """Settings file for the API, or ``None`` when persistence is switched off."""
    raw = os.getenv(AI_SETTINGS_PATH_ENV)
    if raw is None:
        return default_artifacts_root() / "ai_settings.json"
    return Path(raw).expanduser() if raw.strip() else None


class FileBackedAiSettingsStore(InMemoryAiSettingsStore):
    """Keeps the non-secret settings in a JSON file so they survive an API restart.

    The runtime API key is never written; after a restart it has to be entered again.
    """

    def __init__(self, path: Path) -> None:
        super().__init__()
        self._path = path
        self._settings = self._load()

    def update(self, **kwargs: Any) -> AiIntegrationSettings:
        with self._lock:
            self._settings = replace(self._settings, **kwargs)
            self._save(self._settings)
            return self._settings

    def _load(self) -> AiIntegrationSettings:
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return AiIntegrationSettings()
        except (OSError, ValueError) as exc:
            logger.warning("Ignoring unreadable AI settings file %s: %s", self._path, exc)
            return AiIntegrationSettings()
        known = {f.name for f in fields(AiIntegrationSettings)} - _UNPERSISTED_FIELDS
        try:
            settings = AiIntegrationSettings(**{k: v for k, v in raw.items() if k in known})
            settings.to_provider_config().validate()
            settings.to_provider_config().resolved_api_key_env_var()
        except (AttributeError, KeyError, TypeError, ValueError) as exc:
            logger.warning("Ignoring invalid AI settings file %s: %s", self._path, exc)
            return AiIntegrationSettings()
        return settings

    def _save(self, settings: AiIntegrationSettings) -> None:
        payload = {k: v for k, v in asdict(settings).items() if k not in _UNPERSISTED_FIELDS}
        tmp = self._path.with_name(self._path.name + ".tmp")
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            tmp.replace(self._path)
        except OSError as exc:
            logger.warning(
                "Could not save AI settings to %s; they will be lost on restart: %s",
                self._path,
                exc,
            )
