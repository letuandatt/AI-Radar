"""Groq LLM Provider."""

import time
from typing import TypeVar

from pydantic import BaseModel, SecretStr

from app.core.circuit_breaker import CircuitBreaker, CircuitBreakerOpenError
from app.core.cost_tracker import CostTracker
from app.core.retry import retry_on_transient_error
from app.integrations.groq.groq_client import create_groq_chat_model
from app.integrations.llm.logger import LLMLogger

T = TypeVar("T", bound=BaseModel)

# Groq pricing (approximate, per 1M tokens)
GROQ_PRICING = {
    "qwen/qwen3.6-27b": {"input": 0.59, "output": 0.79},  # check lại
}


class GroqProvider:
    """
    Groq LLM Provider.

    Args:
        model_name: Groq model name.
        api_key: Groq API key (from env if None).
        cost_tracker: Optional cost tracker.
        logger: Optional LLM logger.
    """

    def __init__(
        self,
        model_name: str = "qwen/qwen3.6-27b",
        api_key: SecretStr = SecretStr(""),
        cost_tracker: CostTracker | None = None,
        logger: LLMLogger | None = None,
    ) -> None:
        self._model_name = model_name
        self._cost_tracker = cost_tracker
        self._logger = logger
        self._llm = create_groq_chat_model(api_key)
        self._circuit_breaker = CircuitBreaker(
            failure_threshold=5,
            recovery_timeout=60.0,
            name=f"groq-{model_name}",
        )

    def _calculate_cost(self, tokens_in: int, tokens_out: int) -> float:
        """Calculate cost based on Groq pricing."""
        pricing = GROQ_PRICING.get(self._model_name, {"input": 0.59, "output": 0.79})
        cost = (tokens_in / 1_000_000 * pricing["input"]) + (
            tokens_out / 1_000_000 * pricing["output"]
        )
        return cost

    @retry_on_transient_error(
        max_retries=3,
        base_delay=0.5,
        max_delay=30.0,
        exceptions=(Exception,),
    )
    def chat(self, prompt: str, **kwargs: object) -> str:
        if not self._circuit_breaker.allow_request():
            raise CircuitBreakerOpenError(f"Groq circuit breaker is open for {self._model_name}")

        try:
            start_time = time.time()
            response = self._llm.invoke(prompt)
            latency_ms = (time.time() - start_time) * 1000

            tokens_in = getattr(response, "usage_metadata", {}).get("input_tokens", 0)
            tokens_out = getattr(response, "usage_metadata", {}).get("output_tokens", 0)
            cost = self._calculate_cost(tokens_in, tokens_out)

            if self._cost_tracker:
                self._cost_tracker.track("groq", self._model_name, tokens_in, tokens_out, cost)

            if self._logger:
                self._logger.log(
                    provider="groq",
                    model=self._model_name,
                    prompt=prompt,
                    response=response.content,  # type: ignore[arg-type]
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    latency_ms=latency_ms,
                    cost_usd=cost,
                    status="success",
                )

            self._circuit_breaker.record_success()
            return response.content  # type: ignore[return-value]

        except Exception as e:
            self._circuit_breaker.record_failure()
            if self._logger:
                self._logger.log(
                    provider="groq",
                    model=self._model_name,
                    prompt=prompt,
                    response=None,
                    tokens_in=0,
                    tokens_out=0,
                    latency_ms=0.0,
                    cost_usd=0.0,
                    status="error",
                    error_type=type(e).__name__,
                    error_message=str(e),
                )
            raise

    def structured_chat(self, prompt: str, schema: type[T]) -> T:
        if not self._circuit_breaker.allow_request():
            raise CircuitBreakerOpenError(f"Groq circuit breaker is open for {self._model_name}")

        try:
            start_time = time.time()
            structured_llm = self._llm.with_structured_output(schema)
            response = structured_llm.invoke(prompt)
            latency_ms = (time.time() - start_time) * 1000

            tokens_in = 0
            tokens_out = 0
            cost = 0.0

            if self._cost_tracker:
                self._cost_tracker.track("groq", self._model_name, tokens_in, tokens_out, cost)

            if self._logger:
                self._logger.log(
                    provider="groq",
                    model=self._model_name,
                    prompt=prompt,
                    response=str(response.model_dump()),  # type: ignore[union-attr]
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    latency_ms=latency_ms,
                    cost_usd=cost,
                    status="success",
                )

            self._circuit_breaker.record_success()
            return response  # type: ignore[return-value]

        except Exception as e:
            self._circuit_breaker.record_failure()
            if self._logger:
                self._logger.log(
                    provider="groq",
                    model=self._model_name,
                    prompt=prompt,
                    response=None,
                    tokens_in=0,
                    tokens_out=0,
                    latency_ms=0.0,
                    cost_usd=0.0,
                    status="error",
                    error_type=type(e).__name__,
                    error_message=str(e),
                )
            raise

    def get_model_name(self) -> str:
        return self._model_name

    def get_provider_name(self) -> str:
        return "groq"
