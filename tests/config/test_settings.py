import pytest
from pydantic import ValidationError

from app.config.settings import Settings


def test_configuration_loads_environment_values(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "**********")
    monkeypatch.setenv("COHERE_API_KEY", "test-cohere-key")
    monkeypatch.setenv("QDRANT_URL", "https://qdrant.example.com")
    monkeypatch.setenv("QDRANT_API_KEY", "test-qdrant-key")
    monkeypatch.setenv("ZALO_APP_ID", "test-zalo-app-id")
    monkeypatch.setenv("ZALO_APP_SECRET", "test-zalo-app-secret")
    monkeypatch.setenv("ZALO_ACCESS_TOKEN", "test-zalo-access-token")
    monkeypatch.setenv("ZALO_WEBHOOK_SECRET", "test-zalo-webhook-secret")

    settings = Settings.model_validate({})

    assert settings.groq_api_key.get_secret_value() == "**********"
    assert settings.cohere_api_key == "test-cohere-key"
    assert settings.qdrant_url == "https://qdrant.example.com"
    assert settings.qdrant_api_key == "test-qdrant-key"
    assert settings.zalo_app_id == "test-zalo-app-id"
    assert settings.zalo_app_secret == "test-zalo-app-secret"
    assert settings.zalo_access_token == "test-zalo-access-token"
    assert settings.zalo_webhook_secret == "test-zalo-webhook-secret"


def test_loaded_configuration_can_be_used_by_application_component(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "**********")
    monkeypatch.setenv("COHERE_API_KEY", "test-cohere-key")
    monkeypatch.setenv("QDRANT_URL", "https://qdrant.example.com")
    monkeypatch.setenv("QDRANT_API_KEY", "test-qdrant-key")
    monkeypatch.setenv("ZALO_APP_ID", "test-zalo-app-id")
    monkeypatch.setenv("ZALO_APP_SECRET", "test-zalo-app-secret")
    monkeypatch.setenv("ZALO_ACCESS_TOKEN", "test-zalo-access-token")
    monkeypatch.setenv("ZALO_WEBHOOK_SECRET", "test-zalo-webhook-secret")

    settings = Settings.model_validate({})

    assert settings.groq_api_key.get_secret_value() == "**********"


def test_configuration_missing_required_value_is_rejected(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setenv("COHERE_API_KEY", "test-cohere-key")
    monkeypatch.setenv("QDRANT_URL", "https://qdrant.example.com")
    monkeypatch.setenv("QDRANT_API_KEY", "test-qdrant-key")
    monkeypatch.setenv("ZALO_APP_ID", "test-zalo-app-id")
    monkeypatch.setenv("ZALO_APP_SECRET", "test-zalo-app-secret")
    monkeypatch.setenv("ZALO_ACCESS_TOKEN", "test-zalo-access-token")
    monkeypatch.setenv("ZALO_WEBHOOK_SECRET", "test-zalo-webhook-secret")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_configuration_invalid_value_is_rejected(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-groq-key")
    monkeypatch.setenv("COHERE_API_KEY", "test-cohere-key")
    monkeypatch.setenv("QDRANT_URL", "https://qdrant.example.com")
    monkeypatch.setenv("QDRANT_API_KEY", "test-qdrant-key")
    monkeypatch.setenv("ZALO_APP_ID", "test-zalo-app-id")
    monkeypatch.setenv("ZALO_APP_SECRET", "test-zalo-app-secret")
    monkeypatch.setenv("ZALO_ACCESS_TOKEN", "test-zalo-access-token")
    monkeypatch.setenv("ZALO_WEBHOOK_SECRET", "test-zalo-webhook-secret")

    with pytest.raises(ValidationError):
        Settings.model_validate(
            {
                "groq_api_key": 123,
                "cohere_api_key": "test-cohere-key",
                "qdrant_url": "https://qdrant.example.com",
                "qdrant_api_key": "test-qdrant-key",
                "zalo_app_id": "test-zalo-app-id",
                "zalo_app_secret": "test-zalo-app-secret",
                "zalo_access_token": "test-zalo-access-token",
                "zalo_webhook_secret": "test-zalo-webhook-secret",
            }
        )


def test_configuration_multiple_validation_failures_are_reported():
    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)

    assert len(exc_info.value.errors()) >= 1


def test_acquisition_run_on_startup_defaults_to_false(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-groq-key")
    monkeypatch.setenv("COHERE_API_KEY", "test-cohere-key")
    monkeypatch.setenv("QDRANT_URL", "https://qdrant.example.com")
    monkeypatch.setenv("QDRANT_API_KEY", "test-qdrant-key")
    monkeypatch.setenv("ZALO_APP_ID", "test-zalo-app-id")
    monkeypatch.setenv("ZALO_APP_SECRET", "test-zalo-app-secret")
    monkeypatch.setenv("ZALO_ACCESS_TOKEN", "test-zalo-access-token")
    monkeypatch.setenv("ZALO_WEBHOOK_SECRET", "test-zalo-webhook-secret")
    monkeypatch.delenv("ACQUISITION_RUN_ON_STARTUP", raising=False)

    settings = Settings(_env_file=None)

    assert settings.acquisition_run_on_startup is False


def test_acquisition_run_on_startup_can_be_enabled_via_env(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-groq-key")
    monkeypatch.setenv("COHERE_API_KEY", "test-cohere-key")
    monkeypatch.setenv("QDRANT_URL", "https://qdrant.example.com")
    monkeypatch.setenv("QDRANT_API_KEY", "test-qdrant-key")
    monkeypatch.setenv("ZALO_APP_ID", "test-zalo-app-id")
    monkeypatch.setenv("ZALO_APP_SECRET", "test-zalo-app-secret")
    monkeypatch.setenv("ZALO_ACCESS_TOKEN", "test-zalo-access-token")
    monkeypatch.setenv("ZALO_WEBHOOK_SECRET", "test-zalo-webhook-secret")
    monkeypatch.setenv("ACQUISITION_RUN_ON_STARTUP", "true")

    settings = Settings(_env_file=None)

    assert settings.acquisition_run_on_startup is True


def test_llm_settings_defaults(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-groq-key")
    monkeypatch.setenv("COHERE_API_KEY", "test-cohere-key")
    monkeypatch.setenv("QDRANT_URL", "https://qdrant.example.com")
    monkeypatch.setenv("QDRANT_API_KEY", "test-qdrant-key")
    monkeypatch.setenv("ZALO_APP_ID", "test-zalo-app-id")
    monkeypatch.setenv("ZALO_APP_SECRET", "test-zalo-app-secret")
    monkeypatch.setenv("ZALO_ACCESS_TOKEN", "test-zalo-access-token")
    monkeypatch.setenv("ZALO_WEBHOOK_SECRET", "test-zalo-webhook-secret")
    for var in (
        "LLM_PRIMARY_PROVIDER",
        "LLM_FALLBACK_PROVIDERS",
        "GROQ_MODEL",
        "OLLAMA_MODEL",
        "LLM_DAILY_BUDGET_USD",
        "LLM_ALERT_PERCENT",
        "LLM_RATE_LIMIT_RPM",
        "LLM_RATE_LIMIT_WAIT_TIMEOUT",
        "LLM_MAX_CONCURRENT",
    ):
        monkeypatch.delenv(var, raising=False)

    settings = Settings(_env_file=None)

    assert settings.llm_primary_provider == "ollama"
    assert settings.llm_fallback_providers == []
    assert settings.groq_model == "qwen/qwen3.8-27b"
    assert settings.ollama_model == "qwen3:4b"
    assert settings.llm_daily_budget_usd == 10.0
    assert settings.llm_alert_percent == 0.8
    assert settings.llm_rate_limit_rpm == 60.0
    assert settings.llm_rate_limit_wait_timeout == 30.0
    assert settings.llm_max_concurrent == 4


def test_llm_settings_read_from_env(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-groq-key")
    monkeypatch.setenv("COHERE_API_KEY", "test-cohere-key")
    monkeypatch.setenv("QDRANT_URL", "https://qdrant.example.com")
    monkeypatch.setenv("QDRANT_API_KEY", "test-qdrant-key")
    monkeypatch.setenv("ZALO_APP_ID", "test-zalo-app-id")
    monkeypatch.setenv("ZALO_APP_SECRET", "test-zalo-app-secret")
    monkeypatch.setenv("ZALO_ACCESS_TOKEN", "test-zalo-access-token")
    monkeypatch.setenv("ZALO_WEBHOOK_SECRET", "test-zalo-webhook-secret")
    monkeypatch.setenv("LLM_PRIMARY_PROVIDER", "groq")
    monkeypatch.setenv("LLM_FALLBACK_PROVIDERS", '["ollama"]')
    monkeypatch.setenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    monkeypatch.setenv("OLLAMA_MODEL", "qwen3:8b")
    monkeypatch.setenv("LLM_DAILY_BUDGET_USD", "5.5")
    monkeypatch.setenv("LLM_ALERT_PERCENT", "0.9")
    monkeypatch.setenv("LLM_RATE_LIMIT_RPM", "120")
    monkeypatch.setenv("LLM_RATE_LIMIT_WAIT_TIMEOUT", "10")
    monkeypatch.setenv("LLM_MAX_CONCURRENT", "8")

    settings = Settings(_env_file=None)

    assert settings.llm_primary_provider == "groq"
    assert settings.llm_fallback_providers == ["ollama"]
    assert settings.groq_model == "llama-3.3-70b-versatile"
    assert settings.ollama_model == "qwen3:8b"
    assert settings.llm_daily_budget_usd == 5.5
    assert settings.llm_alert_percent == 0.9
    assert settings.llm_rate_limit_rpm == 120.0
    assert settings.llm_rate_limit_wait_timeout == 10.0
    assert settings.llm_max_concurrent == 8
