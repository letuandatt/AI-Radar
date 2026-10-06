"""Tests for LLM providers."""

from unittest.mock import MagicMock, patch

import pytest
from pydantic import BaseModel

from app.core.circuit_breaker import CircuitBreakerOpenError
from app.core.exceptions import PermanentLLMError, TransientLLMError
from app.integrations.llm.groq_provider import GroqProvider
from app.integrations.llm.ollama_provider import OllamaProvider
from app.integrations.llm.provider_chain import LLMProviderChain


class SampleSchema(BaseModel):
    answer: str
    confidence: float


def _structured_result(
    parsed: BaseModel | None = None,
    usage: dict | None = None,
    parsing_error: Exception | None = None,
) -> dict:
    """Build a with_structured_output(include_raw=True) style result."""
    raw_message = MagicMock()
    raw_message.usage_metadata = usage
    return {"raw": raw_message, "parsed": parsed, "parsing_error": parsing_error}


class TestOllamaProvider:
    @patch("app.integrations.llm.ollama_provider.create_ollama_chat_model")
    def test_chat_success(self, mock_create):
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "Test response"
        mock_response.usage_metadata = None
        mock_llm.invoke.return_value = mock_response
        mock_create.return_value = mock_llm

        provider = OllamaProvider(model_name="qwen3:4b")
        result = provider.chat("Hello")

        assert result == "Test response"
        mock_llm.invoke.assert_called_once_with("Hello")

    @patch("app.integrations.llm.ollama_provider.create_ollama_chat_model")
    def test_chat_tracks_metered_tokens_with_zero_cost(self, mock_create):
        mock_response = MagicMock()
        mock_response.content = "Test response"
        mock_response.usage_metadata = {"input_tokens": 120, "output_tokens": 80}
        mock_create.return_value.invoke.return_value = mock_response

        tracker = MagicMock()
        provider = OllamaProvider(model_name="qwen3:4b", cost_tracker=tracker)
        provider.chat("Hello")

        track_args = tracker.track.call_args.args
        assert track_args[2] == 120
        assert track_args[3] == 80
        assert track_args[4] == 0.0  # local Ollama is free

    @patch("app.integrations.llm.ollama_provider.create_ollama_chat_model")
    def test_structured_chat_success(self, mock_create):
        mock_llm = MagicMock()
        mock_structured = MagicMock()
        mock_structured.invoke.return_value = _structured_result(
            parsed=SampleSchema(answer="Yes", confidence=0.9),
            usage={"input_tokens": 50, "output_tokens": 20},
        )
        mock_llm.with_structured_output.return_value = mock_structured
        mock_create.return_value = mock_llm

        provider = OllamaProvider(model_name="qwen3:4b")
        result = provider.structured_chat("Question?", SampleSchema)

        assert result.answer == "Yes"
        assert result.confidence == 0.9
        mock_llm.with_structured_output.assert_called_once_with(SampleSchema, include_raw=True)

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


class TestRetryTaxonomy:
    """Wiring & Fix Plan B3: only transient errors retry at the provider."""

    @patch("app.integrations.llm.groq_provider.create_groq_chat_model")
    def test_transient_error_is_retried(self, mock_create):
        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = [
            TimeoutError("timed out"),
            MagicMock(content="ok", usage_metadata=None),
        ]
        mock_create.return_value = mock_llm

        provider = GroqProvider()
        result = provider.chat("Hello")

        assert result == "ok"
        assert mock_llm.invoke.call_count == 2

    @patch("app.integrations.llm.groq_provider.create_groq_chat_model")
    def test_auth_error_fails_fast_without_retry(self, mock_create):
        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = type("AuthErr", (Exception,), {})("401")
        # Attach a status code so the taxonomy maps it to Permanent.
        error = mock_llm.invoke.side_effect
        error.status_code = 401
        mock_create.return_value = mock_llm

        provider = GroqProvider()

        with pytest.raises(PermanentLLMError):
            provider.chat("Hello")
        assert mock_llm.invoke.call_count == 1  # no retry

    @patch("app.integrations.llm.groq_provider.create_groq_chat_model")
    def test_circuit_breaker_open_is_not_retried(self, mock_create):
        mock_llm = MagicMock()
        mock_create.return_value = mock_llm

        provider = GroqProvider()
        with patch.object(
            provider._circuit_breaker, "allow_request", side_effect=CircuitBreakerOpenError("open")
        ):
            with pytest.raises(CircuitBreakerOpenError):
                provider.chat("Hello")

        mock_llm.invoke.assert_not_called()

    @patch("app.integrations.llm.groq_provider.create_groq_chat_model")
    def test_429_retry_after_overrides_backoff(self, mock_create, monkeypatch):
        sleeps: list[float] = []
        monkeypatch.setattr(
            "app.integrations.llm.groq_provider.time.sleep",
            lambda s: sleeps.append(s),
        )
        rate_limit_error = type("RateLimitErr", (Exception,), {})("429")
        rate_limit_error.status_code = 429
        rate_limit_error.response = type("R", (), {"headers": {"retry-after": "5"}})()

        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = [
            rate_limit_error,
            MagicMock(content="ok", usage_metadata=None),
        ]
        mock_create.return_value = mock_llm

        provider = GroqProvider()
        result = provider.chat("Hello")

        assert result == "ok"
        assert len(sleeps) == 1
        assert sleeps[0] >= 5.0  # Retry-After honored, not the 0.5s backoff


class TestGroqStructuredUsage:
    @patch("app.integrations.llm.groq_provider.create_groq_chat_model")
    def test_structured_chat_tracks_metered_tokens_and_cost(self, mock_create):
        mock_structured = MagicMock()
        mock_structured.invoke.return_value = _structured_result(
            parsed=SampleSchema(answer="Yes", confidence=0.9),
            usage={"input_tokens": 1000, "output_tokens": 500},
        )
        mock_create.return_value.with_structured_output.return_value = mock_structured

        tracker = MagicMock()
        provider = GroqProvider(cost_tracker=tracker)
        result = provider.structured_chat("Question?", SampleSchema)

        assert result.answer == "Yes"
        mock_create.return_value.with_structured_output.assert_called_once_with(
            SampleSchema, include_raw=True
        )

        track_args = tracker.track.call_args.args
        assert track_args[2] == 1000  # tokens_in
        assert track_args[3] == 500  # tokens_out
        assert track_args[4] == pytest.approx(0.000985)  # metered cost > 0

    @patch("app.integrations.llm.groq_provider.create_groq_chat_model")
    def test_structured_chat_estimates_tokens_when_usage_missing(self, mock_create):
        prompt = "a" * 400  # ~100 estimated input tokens
        mock_structured = MagicMock()
        mock_structured.invoke.return_value = _structured_result(
            parsed=SampleSchema(answer="Yes", confidence=0.9),
            usage=None,
        )
        mock_create.return_value.with_structured_output.return_value = mock_structured

        tracker = MagicMock()
        llm_logger = MagicMock()
        provider = GroqProvider(cost_tracker=tracker, logger=llm_logger)
        provider.structured_chat(prompt, SampleSchema)

        track_args = tracker.track.call_args.args
        assert track_args[2] >= 100  # estimated, not 0
        assert track_args[3] >= 1

        log_kwargs = llm_logger.log.call_args.kwargs
        assert log_kwargs["request_type"] == "structured_chat"
        assert log_kwargs["tokens_estimated"] is True

    @patch("app.integrations.llm.groq_provider.create_groq_chat_model")
    def test_structured_chat_raises_on_parsing_error(self, mock_create):
        mock_structured = MagicMock()
        mock_structured.invoke.return_value = _structured_result(parsing_error=ValueError("bad"))
        mock_create.return_value.with_structured_output.return_value = mock_structured

        provider = GroqProvider()

        with pytest.raises(ValueError, match="bad"):
            provider.structured_chat("Question?", SampleSchema)

    @patch("app.integrations.llm.groq_provider.create_groq_chat_model")
    def test_chat_estimates_tokens_when_usage_missing(self, mock_create):
        mock_response = MagicMock()
        mock_response.content = "b" * 200
        mock_response.usage_metadata = None
        mock_create.return_value.invoke.return_value = mock_response

        tracker = MagicMock()
        provider = GroqProvider(cost_tracker=tracker)
        provider.chat("a" * 400)

        track_args = tracker.track.call_args.args
        assert track_args[2] >= 100
        assert track_args[3] >= 50


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

    def test_fallback_on_transient_error(self):
        provider1 = MagicMock()
        provider1.chat.side_effect = TransientLLMError("429 too many requests")
        provider1.get_provider_name.return_value = "provider1"

        provider2 = MagicMock()
        provider2.chat.return_value = "Fallback response"
        provider2.get_provider_name.return_value = "provider2"

        chain = LLMProviderChain([provider1, provider2])
        result = chain.chat("Hello")

        assert result == "Fallback response"

    def test_permanent_error_raises_without_fallback(self):
        provider1 = MagicMock()
        provider1.chat.side_effect = PermanentLLMError("401 unauthorized")
        provider1.get_provider_name.return_value = "provider1"

        provider2 = MagicMock()
        provider2.get_provider_name.return_value = "provider2"

        chain = LLMProviderChain([provider1, provider2])

        with pytest.raises(PermanentLLMError, match="401"):
            chain.chat("Hello")
        provider2.chat.assert_not_called()  # bug must not be masked by fallback

    def test_permanent_error_raises_without_fallback_structured(self):
        provider1 = MagicMock()
        provider1.structured_chat.side_effect = ValueError("schema bug")
        provider1.get_provider_name.return_value = "provider1"

        provider2 = MagicMock()
        provider2.get_provider_name.return_value = "provider2"

        chain = LLMProviderChain([provider1, provider2])

        with pytest.raises(ValueError, match="schema bug"):
            chain.structured_chat("Hello", SampleSchema)
        provider2.structured_chat.assert_not_called()

    def test_all_providers_fail_transient(self):
        provider1 = MagicMock()
        provider1.chat.side_effect = TransientLLMError("Fail 1")
        provider1.get_provider_name.return_value = "provider1"

        provider2 = MagicMock()
        provider2.chat.side_effect = TransientLLMError("Fail 2")
        provider2.get_provider_name.return_value = "provider2"

        chain = LLMProviderChain([provider1, provider2])

        with pytest.raises(TransientLLMError, match="Fail 2"):
            chain.chat("Hello")

    def test_rate_limiter_throttles_calls(self):
        from time import monotonic

        from app.core.rate_limiter import TokenBucket

        provider = MagicMock()
        provider.chat.return_value = "ok"
        provider.get_provider_name.return_value = "test"

        chain = LLMProviderChain(
            [provider],
            rate_limiter=TokenBucket(rate=4.0, capacity=1.0),
        )

        start = monotonic()
        for _ in range(3):
            chain.chat("Hello")
        elapsed = monotonic() - start

        # 1st call uses the initial token; 2 more need 2 × 0.25s of refill.
        assert elapsed >= 0.4

    def test_rate_limiter_timeout_raises_without_calling_llm(self):
        from app.core.exceptions import RateLimitWaitTimeoutError
        from app.core.rate_limiter import TokenBucket

        provider = MagicMock()
        provider.get_provider_name.return_value = "test"

        # Empty bucket, almost no refill — the first acquire must time out.
        chain = LLMProviderChain(
            [provider],
            rate_limiter=TokenBucket(rate=0.001, capacity=0.001),
            rate_limit_wait_timeout=0.3,
        )

        with pytest.raises(RateLimitWaitTimeoutError):
            chain.chat("Hello")
        provider.chat.assert_not_called()
