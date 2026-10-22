from __future__ import annotations

from fastapi.testclient import TestClient

from testo_api.main import create_app
from testo_core.services.failure_analysis_service import FailureAnalysisSummary


class _FakeFailureService:
    def get_summary(self, *, run_id: str) -> FailureAnalysisSummary:
        return FailureAnalysisSummary(
            schema_version="v1",
            run_id=run_id,
            status="no_summary_generated",
            summary_text=None,
            confidence=None,
            limitations=("summary_not_generated",),
            provider=None,
            model=None,
            generated_at=1.0,
            context_stats={},
            error_code="summary_not_available",
        )

    def generate_summary(
        self, *, run_id: str, force_refresh: bool = False
    ) -> FailureAnalysisSummary:  # noqa: ARG002
        return FailureAnalysisSummary(
            schema_version="v1",
            run_id=run_id,
            status="available",
            summary_text="Likely root cause: timeout in upstream service.",
            confidence="medium",
            limitations=(),
            provider="openai",
            model="gpt-4o-mini",
            generated_at=2.0,
            context_stats={"prompt_chars": 150},
            error_code=None,
        )


class _FakeSettingsStore:
    def __init__(self) -> None:
        self._state = {
            "enabled": False,
            "configured": False,
            "provider": "openai",
            "model": "gpt-4o-mini",
            "api_key_source": "env",
            "api_key_env_var": None,
            "key_present": False,
            "timeout_s": 8.0,
            "retry_count": 1,
            "max_input_chars": 16000,
            "max_output_tokens": 300,
            "base_url": None,
        }

    def get(self):  # noqa: ANN001
        class _Settings:
            def __init__(self, state):
                self._state = state

            def to_public_status(self):  # noqa: ANN001
                return dict(self._state)

            api_key_source = "env"

            def to_provider_config(self):  # noqa: ANN001
                class _Cfg:
                    @staticmethod
                    def resolved_api_key_env_var() -> str:
                        return "OPENAI_API_KEY"

                return _Cfg()

        return _Settings(self._state)

    def update(self, **kwargs):  # noqa: ANN003,ANN001
        self._state.update(kwargs)
        return self.get()


def _client() -> TestClient:
    app = create_app()
    from testo_api.dependencies import get_ai_settings_store, get_failure_analysis_service

    app.dependency_overrides[get_failure_analysis_service] = lambda: _FakeFailureService()
    app.dependency_overrides[get_ai_settings_store] = lambda: _FakeSettingsStore()
    return TestClient(app)


def test_get_ai_config_status_contract() -> None:
    resp = _client().get("/api/v1/ai/config/status")
    assert resp.status_code == 200
    payload = resp.json()
    assert set(payload.keys()) == {
        "enabled",
        "configured",
        "provider",
        "model",
        "api_key_source",
        "api_key_env_var",
        "key_present",
        "timeout_s",
        "retry_count",
        "max_input_chars",
        "max_output_tokens",
        "base_url",
    }


def test_generate_run_ai_summary_contract() -> None:
    resp = _client().post("/api/v1/runs/run-1/ai-summary:generate", json={"force_refresh": True})
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["schema_version"] == "v1"
    assert payload["status"] == "available"
    assert payload["provider"] == "openai"


def test_openai_compatible_config_needs_a_base_url_but_no_key() -> None:
    from testo_api.dependencies import get_ai_settings_store
    from testo_core.services.ai.integration_settings import InMemoryAiSettingsStore

    app = create_app()
    store = InMemoryAiSettingsStore()
    app.dependency_overrides[get_ai_settings_store] = lambda: store
    client = TestClient(app)
    body = {"enabled": True, "provider": "openai_compatible", "model": "llama3.2"}

    assert client.put("/api/v1/ai/config", json=body).status_code == 400

    resp = client.put(
        "/api/v1/ai/config", json={**body, "base_url": " http://localhost:11434/v1/ "}
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["base_url"] == "http://localhost:11434/v1"
    assert payload["configured"] is True
    assert payload["key_present"] is False
