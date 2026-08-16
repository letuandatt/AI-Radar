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
