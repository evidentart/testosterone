from __future__ import annotations

import io
import json
import urllib.error

import pytest

from testo_core.services.ai import AiProviderConfig, build_ai_provider
from testo_core.services.ai.provider_base import (
    AiGenerationRequest,
    ProviderMisconfiguredError,
    ProviderUnavailableError,
)


def test_build_openai_provider_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-openai-token")
    config = AiProviderConfig(provider="openai", model="gpt-4o-mini", api_key_source="env")
    provider = build_ai_provider(config=config)
    assert provider.provider_name == "openai"


def test_build_anthropic_provider_from_runtime_key() -> None:
    config = AiProviderConfig(
        provider="anthropic",
        model="claude-3-5-haiku-latest",
        api_key_source="runtime_input",
    )
    provider = build_ai_provider(config=config, runtime_api_key="runtime-token")
    assert provider.provider_name == "anthropic"


def test_missing_env_key_raises_misconfigured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    config = AiProviderConfig(provider="openai", model="gpt-4o-mini", api_key_source="env")
    with pytest.raises(ProviderMisconfiguredError):
        build_ai_provider(config=config)


def test_openai_compatible_requires_an_http_base_url() -> None:
    with pytest.raises(ValueError, match="base_url is required"):
        AiProviderConfig(provider="openai_compatible", model="llama3.2").validate()
    with pytest.raises(ValueError, match="http"):
        AiProviderConfig(
            provider="openai_compatible", model="llama3.2", base_url="file:///etc/passwd"
        ).validate()


@pytest.mark.parametrize(
    ("api_key", "expected_auth"),
    [("", None), ("free-tier-key", "Bearer free-tier-key")],
)
def test_openai_compatible_calls_the_base_url_and_key_is_optional(
    monkeypatch: pytest.MonkeyPatch, api_key: str, expected_auth: str | None
) -> None:
    monkeypatch.delenv("OPENAI_COMPATIBLE_API_KEY", raising=False)
    seen: dict[str, object] = {}

    class _Response:
        def __enter__(self):  # noqa: ANN204
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps(
                {"choices": [{"message": {"content": " Root cause. "}, "finish_reason": "stop"}]}
            ).encode("utf-8")

    def _urlopen(req, timeout):  # noqa: ANN001,ANN202
        seen["url"] = req.full_url
        seen["auth"] = req.get_header("Authorization")
        return _Response()

    monkeypatch.setattr("urllib.request.urlopen", _urlopen)
    config = AiProviderConfig(
        provider="openai_compatible",
        model="llama3.2",
        api_key_source="runtime_input",
        base_url="http://localhost:11434/v1/",
    )
    provider = build_ai_provider(config=config, runtime_api_key=api_key or None)
    result = provider.generate(AiGenerationRequest(prompt="why did it fail?"))

    assert seen == {"url": "http://localhost:11434/v1/chat/completions", "auth": expected_auth}
    assert result.text == "Root cause."
    assert result.provider == "openai_compatible"


def test_http_error_carries_the_providers_own_message(monkeypatch: pytest.MonkeyPatch) -> None:
    body = json.dumps([{"error": {"code": 404, "message": "models/nope is not found."}}])

    def _urlopen(req, timeout):  # noqa: ANN001,ANN202
        raise urllib.error.HTTPError(req.full_url, 404, "Not Found", {}, io.BytesIO(body.encode()))

    monkeypatch.setattr("urllib.request.urlopen", _urlopen)
    provider = build_ai_provider(
        config=AiProviderConfig(
            provider="openai_compatible",
            model="nope",
            api_key_source="runtime_input",
            base_url="https://example.test/v1",
        )
    )
    with pytest.raises(
        ProviderUnavailableError, match=r"HTTP error 404: models/nope is not found\.$"
    ):
        provider.generate(AiGenerationRequest(prompt="x"))
