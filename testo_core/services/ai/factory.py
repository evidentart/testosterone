from __future__ import annotations

from .config import AiProviderConfig
from .provider_base import AiProvider, ProviderUnavailableError
from .providers.anthropic_provider import AnthropicProvider
from .providers.openai_provider import OpenAiCompatibleProvider, OpenAiProvider


def build_ai_provider(
    *, config: AiProviderConfig, runtime_api_key: str | None = None
) -> AiProvider:
    config.validate()
    api_key = config.resolve_api_key(runtime_api_key=runtime_api_key)
    if config.provider == "openai":
        return OpenAiProvider(model=config.model, api_key=api_key, timeout_s=config.timeout_s)
    if config.provider == "anthropic":
        return AnthropicProvider(model=config.model, api_key=api_key, timeout_s=config.timeout_s)
    if config.provider == "openai_compatible":
        return OpenAiCompatibleProvider(
            model=config.model,
            api_key=api_key,
            timeout_s=config.timeout_s,
            base_url=config.base_url or "",
        )
    raise ProviderUnavailableError(f"Unsupported provider: {config.provider}")
