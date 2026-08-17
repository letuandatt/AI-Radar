import pytest
from pydantic import ValidationError

from app.config.settings import Settings


def test_configuration_loads_environment_values(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-groq-key")
    monkeypatch.setenv("COHERE_API_KEY", "test-cohere-key")
    monkeypatch.setenv("QDRANT_URL", "https://qdrant.example.com")
    monkeypatch.setenv("QDRANT_API_KEY", "test-qdrant-key")
    monkeypatch.setenv("ZALO_APP_ID", "test-zalo-app-id")
    monkeypatch.setenv("ZALO_APP_SECRET", "test-zalo-app-secret")
    monkeypatch.setenv("ZALO_ACCESS_TOKEN", "test-zalo-access-token")
    monkeypatch.setenv("ZALO_WEBHOOK_SECRET", "test-zalo-webhook-secret")

    settings = Settings.model_validate({})

    assert settings.groq_api_key == "test-groq-key"
    assert settings.cohere_api_key == "test-cohere-key"
    assert settings.qdrant_url == "https://qdrant.example.com"
    assert settings.qdrant_api_key == "test-qdrant-key"
    assert settings.zalo_app_id == "test-zalo-app-id"
    assert settings.zalo_app_secret == "test-zalo-app-secret"
    assert settings.zalo_access_token == "test-zalo-access-token"
    assert settings.zalo_webhook_secret == "test-zalo-webhook-secret"


def test_loaded_configuration_can_be_used_by_application_component(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "component-test-key")
    monkeypatch.setenv("COHERE_API_KEY", "test-cohere-key")
    monkeypatch.setenv("QDRANT_URL", "https://qdrant.example.com")
    monkeypatch.setenv("QDRANT_API_KEY", "test-qdrant-key")
    monkeypatch.setenv("ZALO_APP_ID", "test-zalo-app-id")
    monkeypatch.setenv("ZALO_APP_SECRET", "test-zalo-app-secret")
    monkeypatch.setenv("ZALO_ACCESS_TOKEN", "test-zalo-access-token")
    monkeypatch.setenv("ZALO_WEBHOOK_SECRET", "test-zalo-webhook-secret")

    settings = Settings.model_validate({})

    assert settings.groq_api_key == "component-test-key"


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

    assert len(exc_info.value.errors()) == 8
