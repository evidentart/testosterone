from __future__ import annotations

import json
import urllib.error
import urllib.request

from testo_core.security.redaction import redact_error_message, redact_text

from ..provider_base import (
    AiGenerationRequest,
    AiGenerationResult,
    AiProvider,
    AiProviderName,
    ProviderMisconfiguredError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    UnsupportedProviderModelError,
)


def _error_detail(exc: urllib.error.HTTPError) -> str:
    """The provider's own explanation (wrong model name, bad path), redacted and kept short."""
    try:
        raw = exc.read(4000).decode("utf-8", errors="replace")
    except (OSError, ValueError):
        return ""
    try:
        body = json.loads(raw)
    except ValueError:
        body = None
    if isinstance(body, list) and body:
        body = body[0]
    error = body.get("error") if isinstance(body, dict) else None
    message = error.get("message") if isinstance(error, dict) else error
    text = " ".join(str(message or "").split())
    return f": {redact_text(text)[:300].rstrip('.')}" if text else ""


class OpenAiProvider(AiProvider):
    provider_name: AiProviderName = "openai"
    _label = "OpenAI"

    def __init__(
        self,
        *,
        model: str,
        api_key: str,
        timeout_s: float,
        base_url: str = "https://api.openai.com/v1",
    ) -> None:
        self.model = model
        self._api_key = api_key
        self._timeout_s = timeout_s
        self._base_url = base_url.rstrip("/")

    def generate(self, request: AiGenerationRequest) -> AiGenerationResult:
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": request.prompt}],
            "max_tokens": request.max_output_tokens,
            "temperature": request.temperature,
        }
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        req = urllib.request.Request(
            url=f"{self._base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout_s) as response:  # nosec: B310
                body = json.loads(response.read().decode("utf-8"))
        except TimeoutError as exc:
            raise ProviderTimeoutError(f"{self._label} request timed out.") from exc
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                raise ProviderRateLimitError(f"{self._label} rate limit exceeded.") from exc
            if exc.code in (401, 403):
                raise ProviderMisconfiguredError(
                    f"{self._label} rejected the API key (HTTP {exc.code})."
                ) from exc
            if exc.code == 400:
                raise UnsupportedProviderModelError(
                    f"{self._label} model is unsupported for this key."
                ) from exc
            raise ProviderUnavailableError(
                f"{self._label} HTTP error {exc.code}{_error_detail(exc)}."
            ) from exc
        except urllib.error.URLError as exc:
            raise ProviderUnavailableError(
                f"{self._label} request failed: {redact_error_message(exc)}"
            ) from exc
        text = (
            body.get("choices", [{}])[0].get("message", {}).get("content")
            if isinstance(body.get("choices"), list)
            else None
        )
        if not text:
            raise ProviderUnavailableError(
                f"{self._label} response did not include summary content."
            )
        usage = body.get("usage", {}) if isinstance(body.get("usage"), dict) else {}
        return AiGenerationResult(
            text=str(text).strip(),
            provider=self.provider_name,
            model=self.model,
            finish_reason=body.get("choices", [{}])[0].get("finish_reason")
            if isinstance(body.get("choices"), list)
            else None,
            usage_input_tokens=usage.get("prompt_tokens"),
            usage_output_tokens=usage.get("completion_tokens"),
        )


class OpenAiCompatibleProvider(OpenAiProvider):
    """OpenAI's chat-completions API served from another base URL (Ollama, Groq, ...)."""

    provider_name: AiProviderName = "openai_compatible"
    _label = "OpenAI-compatible provider"
