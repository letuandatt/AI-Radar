"""Tests for LLM provider factory and settings-driven bootstrap wiring."""

from unittest.mock import MagicMock, patch

import pytest
from pydantic import SecretStr

from app.integrations.llm.factory import LLMProviderFactory
from app.services.repository.bootstrap import create_analysis_service, create_llm_chain


@patch("app.integrations.llm.ollama_provider.create_ollama_chat_model")
@patch("app.integrations.llm.groq_provider.create_groq_chat_model")
def test_factory_creates_groq_first_chain_with_configured_models(
    mock_groq_create, mock_ollama_create
):
    chain = LLMProviderFactory.create(
        primary_provider="groq",
        fallback_providers=["ollama"],
        groq_model="llama-3.3-70b-versatile",
        ollama_model="qwen3:8b",
        groq_api_key=SecretStr("test-key"),
    )

    assert chain.get_provider_name() == "groq"
    assert chain.get_model_name() == "llama-3.3-70b-versatile"
    assert chain._providers[1].get_provider_name() == "ollama"
    assert chain._providers[1].get_model_name() == "qwen3:8b"

    mock_groq_create.assert_called_once()
    assert mock_groq_create.call_args.kwargs["model"] == "llama-3.3-70b-versatile"
    mock_ollama_create.assert_called_once_with("qwen3:8b")


@patch("app.integrations.llm.ollama_provider.create_ollama_chat_model")
def test_factory_order_follows_primary_provider(mock_ollama_create):
    chain = LLMProviderFactory.create(
        primary_provider="ollama",
        fallback_providers=["groq"],
        groq_api_key=SecretStr("test-key"),
    )

    assert chain.get_provider_name() == "ollama"
    assert chain._providers[1].get_provider_name() == "groq"


@patch("app.integrations.llm.ollama_provider.create_ollama_chat_model")
@patch("app.integrations.llm.groq_provider.create_groq_chat_model")
def test_factory_passes_budget_to_cost_tracker(mock_groq_create, mock_ollama_create):
    with patch("app.integrations.llm.factory.CostTracker", autospec=True) as mock_cost_tracker_cls:
        LLMProviderFactory.create(
            primary_provider="groq",
            fallback_providers=["ollama"],
            daily_budget_usd=5.5,
            alert_percent=0.9,
            groq_api_key=SecretStr("test-key"),
        )

        mock_cost_tracker_cls.assert_called_once_with(
            daily_budget_usd=5.5,
            alert_percent=0.9,
            daily_token_limit=None,
            daily_request_limit=None,
        )


@patch("app.services.repository.bootstrap.ContentAnalyzer")
@patch("app.services.repository.access_service.RepositoryAccessService")
@patch("app.services.repository.bootstrap.get_settings")
def test_create_analysis_service_uses_injected_chain(
    mock_get_settings,
    mock_access_cls,
    mock_analyzer_cls,
):
    """Analysis must use the SHARED chain — one budget across workloads."""
    mock_settings = MagicMock()
    mock_settings.llm_max_concurrent = 8
    mock_get_settings.return_value = mock_settings

    llm_chain = MagicMock(name="shared_llm_chain")

    create_analysis_service(MagicMock(name="initializer"), llm_chain)

    kwargs = mock_analyzer_cls.call_args.kwargs
    assert kwargs["llm_provider"] is llm_chain
    assert kwargs["max_concurrent"] == 8


@patch("app.integrations.llm.factory.LLMProviderFactory.create")
@patch("app.services.repository.bootstrap.get_settings")
def test_create_llm_chain_uses_settings(mock_get_settings, mock_factory_create):
    """create_llm_chain builds the one shared chain fully from settings."""
    mock_settings = MagicMock()
    mock_settings.llm_primary_provider = "groq"
    mock_settings.llm_fallback_providers = ["ollama"]
    mock_settings.groq_model = "llama-3.3-70b-versatile"
    mock_settings.ollama_model = "qwen3:8b"
    mock_settings.groq_api_key = SecretStr("test-key")
    mock_settings.llm_daily_budget_usd = 5.5
    mock_settings.llm_alert_percent = 0.9
    mock_settings.llm_rate_limit_rpm = 120.0
    mock_settings.llm_rate_limit_wait_timeout = 10.0
    mock_settings.llm_daily_token_limit = 500000
    mock_settings.llm_daily_request_limit = 1000
    mock_get_settings.return_value = mock_settings

    create_llm_chain(mock_settings)

    mock_factory_create.assert_called_once_with(
        primary_provider="groq",
        fallback_providers=["ollama"],
        ollama_model="qwen3:8b",
        groq_model="llama-3.3-70b-versatile",
        groq_api_key=SecretStr("test-key"),
        daily_budget_usd=5.5,
        alert_percent=0.9,
        rate_limit_rpm=120.0,
        rate_limit_wait_timeout=10.0,
        daily_token_limit=500000,
        daily_request_limit=1000,
    )


@patch("app.integrations.llm.ollama_provider.create_ollama_chat_model")
def test_factory_attaches_rate_limiter_when_configured(mock_ollama_create):
    from app.core.rate_limiter import TokenBucket

    chain = LLMProviderFactory.create(
        primary_provider="ollama",
        rate_limit_rpm=60.0,
    )

    assert chain._rate_limiter is not None
    assert isinstance(chain._rate_limiter, TokenBucket)
    assert chain._rate_limiter.rate == pytest.approx(1.0)

    chain_disabled = LLMProviderFactory.create(primary_provider="ollama", rate_limit_rpm=0)
    assert chain_disabled._rate_limiter is None
