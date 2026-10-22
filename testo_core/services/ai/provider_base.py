from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

AiProviderName = Literal["openai", "anthropic", "openai_compatible"]


@dataclass(frozen=True)
class AiGenerationRequest:
    prompt: str
    max_output_tokens: int = 300
    temperature: float = 0.1


@dataclass(frozen=True)
class AiGenerationResult:
    text: str
    provider: AiProviderName
    model: str
    finish_reason: str | None = None
    usage_input_tokens: int | None = None
    usage_output_tokens: int | None = None


class AiProviderError(RuntimeError):
    pass


class ProviderMisconfiguredError(AiProviderError):
    pass


class ProviderTimeoutError(AiProviderError):
    pass


class ProviderRateLimitError(AiProviderError):
    pass


class UnsupportedProviderModelError(AiProviderError):
    pass


class ProviderUnavailableError(AiProviderError):
    pass


class AiProvider(Protocol):
    provider_name: AiProviderName
    model: str

    def generate(self, request: AiGenerationRequest) -> AiGenerationResult: ...
