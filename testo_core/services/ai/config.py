from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Literal

from .provider_base import AiProviderName, ProviderMisconfiguredError

ApiKeySource = Literal["env", "runtime_input"]

_DEFAULT_KEY_ENV_VARS: dict[AiProviderName, str] = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "openai_compatible": "OPENAI_COMPATIBLE_API_KEY",
}

_ENV_VAR_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

# Any server that speaks OpenAI's chat-completions API at a custom base URL: a local
# Ollama, or a hosted service such as Groq, OpenRouter or Gemini. A local server needs
# no key, so the key is optional for this provider.
OPENAI_COMPATIBLE: AiProviderName = "openai_compatible"


@dataclass(frozen=True)
class AiProviderConfig:
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

    def resolved_api_key_env_var(self) -> str:
        return self.api_key_env_var or _DEFAULT_KEY_ENV_VARS[self.provider]

    def validate(self) -> None:
        if self.timeout_s <= 0:
            raise ValueError("timeout_s must be greater than zero.")
        if self.retry_count < 0:
            raise ValueError("retry_count cannot be negative.")
        if self.max_input_chars <= 0:
            raise ValueError("max_input_chars must be greater than zero.")
        if self.max_output_tokens <= 0:
            raise ValueError("max_output_tokens must be greater than zero.")
        if self.api_key_source == "env" and not self.resolved_api_key_env_var():
            raise ValueError("api_key_env_var must be provided when api_key_source=env.")
        if self.api_key_env_var and not _ENV_VAR_NAME.fullmatch(self.api_key_env_var):
            # Catches a key pasted into the name field, which would then be shown back in clear.
            raise ValueError(
                "api_key_env_var must be the name of an environment variable, not the key itself."
            )
        if self.provider == OPENAI_COMPATIBLE:
            if not self.base_url:
                raise ValueError("base_url is required for an OpenAI-compatible provider.")
            if not self.base_url.startswith(("http://", "https://")):
                raise ValueError("base_url must start with http:// or https://.")

    def resolve_api_key(self, *, runtime_api_key: str | None = None) -> str:
        if self.api_key_source == "runtime_input":
            if runtime_api_key:
                return runtime_api_key
            if self.provider == OPENAI_COMPATIBLE:
                return ""
            raise ProviderMisconfiguredError("Runtime API key is required but missing.")
        key = os.getenv(self.resolved_api_key_env_var(), "")
        if key or self.provider == OPENAI_COMPATIBLE:
            return key
        raise ProviderMisconfiguredError(
            f"Environment API key is missing: {self.resolved_api_key_env_var()}"
        )
