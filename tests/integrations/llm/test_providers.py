"""Tests for LLM providers."""

from unittest.mock import MagicMock, patch

import pytest
from pydantic import BaseModel

from app.core.circuit_breaker import CircuitBreakerOpenError
from app.integrations.llm.ollama_provider import OllamaProvider
from app.integrations.llm.provider_chain import LLMProviderChain


class SampleSchema(BaseModel):
    answer: str
    confidence: float


class TestOllamaProvider:
    @patch("app.integrations.llm.ollama_provider.create_ollama_chat_model")
    def test_chat_success(self, mock_create):
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "Test response"
        mock_llm.invoke.return_value = mock_response
        mock_create.return_value = mock_llm

        provider = OllamaProvider(model_name="qwen3:4b")
        result = provider.chat("Hello")

        assert result == "Test response"
        mock_llm.invoke.assert_called_once_with("Hello")

    @patch("app.integrations.llm.ollama_provider.create_ollama_chat_model")
    def test_structured_chat_success(self, mock_create):
        mock_llm = MagicMock()
        mock_structured = MagicMock()
        mock_structured.invoke.return_value = SampleSchema(answer="Yes", confidence=0.9)
        mock_llm.with_structured_output.return_value = mock_structured
        mock_create.return_value = mock_llm

        provider = OllamaProvider(model_name="qwen3:4b")
        result = provider.structured_chat("Question?", SampleSchema)

        assert result.answer == "Yes"
        assert result.confidence == 0.9

    @patch("app.integrations.llm.ollama_provider.create_ollama_chat_model")
    def test_circuit_breaker_opens(self, mock_create):
        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = Exception("Connection error")
        mock_create.return_value = mock_llm

        provider = OllamaProvider(model_name="qwen3:4b")
        provider._circuit_breaker._failure_threshold = 2

        with pytest.raises(Exception):
            provider.chat("Test 1")
        with pytest.raises(Exception):
            provider.chat("Test 2")

        with pytest.raises(CircuitBreakerOpenError):
            provider.chat("Test 3")


class TestLLMProviderChain:
    def test_single_provider_success(self):
        mock_provider = MagicMock()
        mock_provider.chat.return_value = "Response"
        mock_provider.get_provider_name.return_value = "test"

        chain = LLMProviderChain([mock_provider])
        result = chain.chat("Hello")

        assert result == "Response"

    def test_fallback_on_circuit_breaker(self):
        provider1 = MagicMock()
        provider1.chat.side_effect = CircuitBreakerOpenError("Open")
        provider1.get_provider_name.return_value = "provider1"

        provider2 = MagicMock()
        provider2.chat.return_value = "Fallback response"
        provider2.get_provider_name.return_value = "provider2"

        chain = LLMProviderChain([provider1, provider2])
        result = chain.chat("Hello")

        assert result == "Fallback response"

    def test_all_providers_fail(self):
        provider1 = MagicMock()
        provider1.chat.side_effect = Exception("Fail 1")
        provider1.get_provider_name.return_value = "provider1"

        provider2 = MagicMock()
        provider2.chat.side_effect = Exception("Fail 2")
        provider2.get_provider_name.return_value = "provider2"

        chain = LLMProviderChain([provider1, provider2])

        with pytest.raises(Exception, match="Fail 2"):
            chain.chat("Hello")
