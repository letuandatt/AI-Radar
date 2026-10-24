"""Settings/factory/registry wiring must not run identification on startup."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.config.settings import Settings
from app.core import application
from app.core.lifecycle import ApplicationLifecycle
from app.services.repository import bootstrap
from app.services.trend.identifier import TrendIdentifier


def test_factory_uses_setting_and_never_creates_llm(monkeypatch):
    llm = MagicMock(side_effect=AssertionError("Trend must not request an LLM"))
    monkeypatch.setattr(bootstrap, "create_llm_chain", llm)
    initializer = MagicMock()
    settings = SimpleNamespace(trend_min_count=7)
    trend = bootstrap.create_trend_service(initializer, settings)
    assert isinstance(trend, TrendIdentifier)
    initializer.sqlite_store.query_trend_items.assert_not_called()
    llm.assert_not_called()
    with pytest.raises(ValueError):
        bootstrap.create_trend_service(initializer, SimpleNamespace(trend_min_count=0))


def test_trend_setting_default_and_environment(monkeypatch):
    values = dict(
        groq_api_key="test",
        cohere_api_key="test",
        qdrant_url="http://unused",
        qdrant_api_key="test",
        zalo_app_id="test",
        zalo_app_secret="test",
        zalo_access_token="test",
        zalo_webhook_secret="test",
    )
    monkeypatch.delenv("TREND_MIN_COUNT", raising=False)
    assert Settings(_env_file=None, **values).trend_min_count == 3
    monkeypatch.setenv("TREND_MIN_COUNT", "7")
    assert Settings(_env_file=None, **values).trend_min_count == 7
    monkeypatch.setenv("TREND_MIN_COUNT", "0")
    with pytest.raises(ValueError):
        Settings(_env_file=None, **values)


def test_registry_registers_trend_at_42_and_factory_uses_repository(monkeypatch):
    registry = MagicMock()
    monkeypatch.setattr(application, "ComponentRegistry", lambda: registry)
    monkeypatch.setattr(application, "_registry", None)
    lifecycle = ApplicationLifecycle()
    application.start_application(lifecycle)
    registrations = {call.args[0]: call for call in registry.register.call_args_list}
    assert registrations["trend"].kwargs["priority"] == 42
    assert registrations["processing"].kwargs["priority"] == 38
    factory = MagicMock()
    settings = object()
    monkeypatch.setattr(application, "create_trend_service", factory)
    monkeypatch.setattr(application, "get_settings", lambda: settings)
    init = registrations["trend"].args[1]
    assert init() is factory.return_value
    factory.assert_called_once_with(registry.get_component.return_value, settings)
    registry.get_component.assert_called_once_with("repository")
    factory.return_value.get_weekly_trends.assert_not_called()
    application.shutdown_application(lifecycle)
