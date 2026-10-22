from __future__ import annotations

import pytest

from testo_core.services.ai import AiProviderConfig


def test_ai_config_validation_rejects_invalid_limits() -> None:
    with pytest.raises(ValueError):
        AiProviderConfig(timeout_s=0).validate()
    with pytest.raises(ValueError):
        AiProviderConfig(retry_count=-1).validate()
    with pytest.raises(ValueError):
        AiProviderConfig(max_input_chars=0).validate()


def test_ai_config_rejects_a_key_pasted_as_the_env_var_name() -> None:
    with pytest.raises(ValueError, match="not the key itself"):
        AiProviderConfig(api_key_env_var="sk-proj.abc-123").validate()
    AiProviderConfig(api_key_env_var="MY_TEAM_OPENAI_KEY").validate()
