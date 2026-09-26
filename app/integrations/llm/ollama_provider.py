"""Ollama LLM Provider - wraps existing ollama_client."""

import time
from typing import TypeVar

from pydantic import BaseModel

from app.core.circuit_breaker import CircuitBreaker, CircuitBreakerOpenError
from app.core.cost_tracker import CostTracker
from app.core.retry import retry_on_transient_error
from app.integrations.llm.logger import LLMLogger
from app.integrations.ollama.ollama_client import create_ollama_chat_model

T = TypeVar("T", bound=BaseModel)


class OllamaProvider:
    """
    Ollama LLM Provider.

    Wraps the existing create_ollama_chat_model() function.

    Args:
        model_name: Ollama model name (default: qwen3:4b).
        cost_tracker: Optional cost tracker.
        logger: Optional LLM logger.
    """

    def __init__(
        self,
        model_name: str = "qwen3:4b",
        cost_tracker: CostTracker | None = None,
        logger: LLMLogger | None = None,
    ) -> None:
        self._model_name = model_name
        self._cost_tracker = cost_tracker
        self._logger = logger
        self._llm = create_ollama_chat_model(model_name)
        self._circuit_breaker = CircuitBreaker(
            failure_threshold=5,
            recovery_timeout=60.0,
            name=f"ollama-{model_name}",
        )

    @retry_on_transient_error(
        max_retries=3,
        base_delay=0.5,
        max_delay=30.0,
        exceptions=(Exception,),
    )
    def chat(self, prompt: str, **kwargs: object) -> str:
        if not self._circuit_breaker.allow_request():
            raise CircuitBreakerOpenError(f"Ollama circuit breaker is open for {self._model_name}")

        try:
            start_time = time.time()
            response = self._llm.invoke(prompt)
            latency_ms = (time.time() - start_time) * 1000

            # Ollama local = $0
            if self._cost_tracker:
                self._cost_tracker.track("ollama", self._model_name, 0, 0, 0.0)

            if self._logger:
                self._logger.log(
                    provider="ollama",
                    model=self._model_name,
                    prompt=prompt,
                    response=response.content,  # type: ignore[arg-type]
                    tokens_in=0,
                    tokens_out=0,
                    latency_ms=latency_ms,
                    cost_usd=0.0,
                    status="success",
                )

            self._circuit_breaker.record_success()
            return response.content  # type: ignore[return-value]

        except Exception as e:
            self._circuit_breaker.record_failure()
            if self._logger:
                self._logger.log(
                    provider="ollama",
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
            raise CircuitBreakerOpenError(f"Ollama circuit breaker is open for {self._model_name}")

        try:
            start_time = time.time()
            structured_llm = self._llm.with_structured_output(schema)
            response = structured_llm.invoke(prompt)
            latency_ms = (time.time() - start_time) * 1000

            if self._cost_tracker:
                self._cost_tracker.track("ollama", self._model_name, 0, 0, 0.0)

            if self._logger:
                self._logger.log(
                    provider="ollama",
                    model=self._model_name,
                    prompt=prompt,
                    response=str(response.model_dump()),  # type: ignore[union-attr]
                    tokens_in=0,
                    tokens_out=0,
                    latency_ms=latency_ms,
                    cost_usd=0.0,
                    status="success",
                )

            self._circuit_breaker.record_success()
            return response  # type: ignore[return-value]

        except Exception as e:
            self._circuit_breaker.record_failure()
            if self._logger:
                self._logger.log(
                    provider="ollama",
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
        return "ollama"
