"""Shared-chain wiring, nested environment config and no eager scoring."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.config.settings import Settings
from app.core import application
from app.core.lifecycle import ApplicationLifecycle
from app.services.importance.config import ImportanceConfig
from app.services.repository import bootstrap


def test_factory_injects_existing_chain_without_creating_a_provider(monkeypatch):
    forbidden = MagicMock(side_effect=AssertionError("No independent chain"))
    monkeypatch.setattr(bootstrap, "create_llm_chain", forbidden)
    initializer, chain = MagicMock(), MagicMock()
    scorer = bootstrap.create_importance_service(
        initializer, chain, SimpleNamespace(importance=ImportanceConfig())
    )
    assert scorer._provider is chain
    initializer.sqlite_store.load_importance_inputs.assert_not_called()
    chain.structured_chat.assert_not_called()
    forbidden.assert_not_called()


def test_registry_priority_and_shared_dependencies(monkeypatch):
    registry = MagicMock()
    monkeypatch.setattr(application, "ComponentRegistry", lambda: registry)
    monkeypatch.setattr(application, "_registry", None)
    lifecycle = ApplicationLifecycle()
    application.start_application(lifecycle)
    registrations = {call.args[0]: call for call in registry.register.call_args_list}
    assert registrations["importance"].kwargs["priority"] == 43
    factory = MagicMock()
    settings = object()
    monkeypatch.setattr(application, "create_importance_service", factory)
    monkeypatch.setattr(application, "get_settings", lambda: settings)
    initializer, chain = object(), object()
    registry.get_component.side_effect = lambda name: {
        "repository": initializer,
        "llm_chain": chain,
    }[name]
    assert registrations["importance"].args[1]() is factory.return_value
    factory.assert_called_once_with(initializer, chain, settings)
    factory.return_value.score_batch.assert_not_called()
    application.shutdown_application(lifecycle)


def test_nested_environment_config(monkeypatch):
    values = dict(
        groq_api_key="test",
        cohere_api_key="test",
        qdrant_url="unused",
        qdrant_api_key="test",
        zalo_app_id="test",
        zalo_app_secret="test",
        zalo_access_token="test",
        zalo_webhook_secret="test",
    )
    monkeypatch.setenv(
        "IMPORTANCE", '{"llm_top_n": 2, "source_authorities": {"github:example": 0.8}}'
    )
    settings = Settings(_env_file=None, **values)
    assert settings.importance.llm_top_n == 2
    assert settings.importance.source_authorities["github:example"] == 0.8
    monkeypatch.setenv("IMPORTANCE", '{"weight_relevance": 0.9}')
    with pytest.raises(ValueError):
        Settings(_env_file=None, **values)
