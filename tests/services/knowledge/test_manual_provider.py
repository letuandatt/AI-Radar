"""Manual adds use Groq without changing the batch provider policy."""

from unittest.mock import Mock, patch

import pytest
from pydantic import BaseModel, SecretStr

from app.config.settings import Settings
from app.core.cost_tracker import CostTracker
from app.core.exceptions import BudgetExceededError, TransientLLMError
from app.integrations.llm.provider_chain import LLMProviderChain
from app.services.repository.bootstrap import create_manual_llm_chain


def settings():
    return Settings.model_construct(
        groq_api_key=SecretStr("test-key"),
        groq_model="configured-api-model",
        llm_primary_provider="ollama",
        llm_fallback_providers=["groq", "ollama"],
        llm_daily_budget_usd=0.5,
        llm_rate_limit_rpm=12,
        llm_daily_request_limit=20,
        llm_daily_token_limit=10_000,
    )


def test_standalone_keeps_limits_and_never_constructs_ollama():
    config = settings()
    with (
        patch("app.integrations.llm.factory.GroqProvider") as groq,
        patch("app.integrations.llm.factory.OllamaProvider") as ollama,
    ):
        chain = create_manual_llm_chain(config)
    assert chain._providers == [groq.return_value]
    assert chain.cost_tracker.daily_budget_usd == 0.5
    assert chain.cost_tracker.daily_request_limit == 20
    assert chain.cost_tracker.daily_token_limit == 10_000
    assert chain._rate_limiter is not None
    assert config.llm_primary_provider == "ollama"
    assert config.llm_fallback_providers == ["groq", "ollama"]
    assert groq.call_args.kwargs["model_name"] == "configured-api-model"
    ollama.assert_not_called()
    groq.return_value.structured_chat.assert_not_called()


def test_main_shares_controls_and_does_not_fall_back():
    tracker = CostTracker(daily_budget_usd=0.5)
    limiter, local, remote = Mock(), Mock(), Mock()
    remote.estimate_cost.return_value = 0.1
    remote.structured_chat.side_effect = TransientLLMError("API unavailable")
    original = LLMProviderChain([local], rate_limiter=limiter, cost_tracker=tracker)
    with patch("app.integrations.llm.factory.GroqProvider", return_value=remote) as groq:
        manual = create_manual_llm_chain(settings(), shared_chain=original)
    assert manual.cost_tracker is tracker
    assert groq.call_args.kwargs["cost_tracker"] is tracker
    assert original._providers == [local]
    with pytest.raises(TransientLLMError):
        manual.structured_chat("article", BaseModel)
    limiter.wait_and_acquire.assert_called_once_with(timeout=30.0)
    local.structured_chat.assert_not_called()

    remote.structured_chat.reset_mock()
    tracker.current_cost = 0.5
    with pytest.raises(BudgetExceededError):
        manual.structured_chat("article", BaseModel)
    remote.structured_chat.assert_not_called()
    local.structured_chat.assert_not_called()


@pytest.mark.parametrize("field,value", [("groq_api_key", SecretStr(" ")), ("groq_model", " ")])
def test_missing_api_configuration_fails_before_provider_creation(field, value):
    config = settings().model_copy(update={field: value})
    with patch("app.services.repository.bootstrap.create_llm_chain") as factory:
        with pytest.raises(ValueError, match="Manual add requires GROQ_"):
            create_manual_llm_chain(config)
    factory.assert_not_called()


def test_main_web_wires_manual_chain_only(monkeypatch):
    from app.core import application

    registry, manual = Mock(), Mock()
    config = settings()
    monkeypatch.setattr(application, "_registry", registry)
    monkeypatch.setattr(application, "get_settings", lambda: config)
    with (
        patch("app.api.config.WebConfig", return_value=Mock(enabled=True)),
        patch("app.api.bootstrap.start_web") as start,
        patch(
            "app.services.repository.bootstrap.create_manual_llm_chain", return_value=manual
        ) as factory,
    ):
        application._init_web()
    factory.assert_called_once_with(config, shared_chain=registry.get_component.return_value)
    assert start.call_args.kwargs["llm_chain"] is manual
    assert start.call_args.kwargs["importance_config"] is config.importance
