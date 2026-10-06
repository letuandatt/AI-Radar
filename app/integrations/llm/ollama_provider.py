"""Ollama LLM Provider - wraps existing ollama_client."""

import time
from typing import TypeVar, cast

from pydantic import BaseModel

from app.core.circuit_breaker import CircuitBreaker, CircuitBreakerOpenError
from app.core.cost_tracker import CostTracker
from app.core.exceptions import TransientLLMError
from app.core.retry import retry_on_transient_error
from app.integrations.llm.error_taxonomy import classify_llm_error
from app.integrations.llm.logger import LLMLogger
from app.integrations.llm.usage import estimate_tokens, read_usage
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
        exceptions=(TransientLLMError,),
    )
    def chat(self, prompt: str, **kwargs: object) -> str:
        if not self._circuit_breaker.allow_request():
            raise CircuitBreakerOpenError(f"Ollama circuit breaker is open for {self._model_name}")

        try:
            start_time = time.time()
            try:
                response = self._llm.invoke(prompt)
            except CircuitBreakerOpenError:
                raise
            except Exception as e:
                raise classify_llm_error(e) from e
            latency_ms = (time.time() - start_time) * 1000

            response_text = self._content_to_str(response.content)
            tokens_in, tokens_out = read_usage(response)
            tokens_estimated = False
            if tokens_in == 0 and tokens_out == 0:
                tokens_in, tokens_out = estimate_tokens(prompt, response_text)
                tokens_estimated = True

            # Ollama local = $0, but token counts are still tracked for throughput
            if self._cost_tracker:
                self._cost_tracker.track("ollama", self._model_name, tokens_in, tokens_out, 0.0)

            if self._logger:
                self._logger.log(
                    provider="ollama",
                    model=self._model_name,
                    prompt=prompt,
                    response=response_text,
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    latency_ms=latency_ms,
                    cost_usd=0.0,
                    status="success",
                    request_type="chat",
                    tokens_estimated=tokens_estimated,
                )

            self._circuit_breaker.record_success()
            return response_text

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
                    request_type="chat",
                )
            raise

    def structured_chat(self, prompt: str, schema: type[T]) -> T:
        if not self._circuit_breaker.allow_request():
            raise CircuitBreakerOpenError(f"Ollama circuit breaker is open for {self._model_name}")

        try:
            start_time = time.time()
            # include_raw=True keeps the AIMessage (and its usage_metadata)
            # alongside the parsed schema object, enabling real token accounting.
            structured_llm = self._llm.with_structured_output(schema, include_raw=True)
            # include_raw=True guarantees a dict result, but LangChain's type
            # stubs widen it to dict | BaseModel — narrow for mypy.
            try:
                raw_result = cast("dict[str, object]", structured_llm.invoke(prompt))
            except CircuitBreakerOpenError:
                raise
            except Exception as e:
                raise classify_llm_error(e) from e
            latency_ms = (time.time() - start_time) * 1000

            parsed = raw_result.get("parsed")
            parsing_error = raw_result.get("parsing_error")
            if parsing_error is not None:
                raise cast(BaseException, parsing_error)
            if parsed is None:
                raise ValueError("Structured output parsing failed")

            response_text = (
                parsed.model_dump_json() if isinstance(parsed, BaseModel) else str(parsed)
            )

            tokens_in, tokens_out = read_usage(raw_result.get("raw"))
            tokens_estimated = False
            if tokens_in == 0 and tokens_out == 0:
                tokens_in, tokens_out = estimate_tokens(prompt, response_text)
                tokens_estimated = True

            # Ollama local = $0, but token counts are still tracked for throughput
            if self._cost_tracker:
                self._cost_tracker.track("ollama", self._model_name, tokens_in, tokens_out, 0.0)

            if self._logger:
                self._logger.log(
                    provider="ollama",
                    model=self._model_name,
                    prompt=prompt,
                    response=response_text,
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    latency_ms=latency_ms,
                    cost_usd=0.0,
                    status="success",
                    request_type="structured_chat",
                    tokens_estimated=tokens_estimated,
                )

            self._circuit_breaker.record_success()
            return cast(T, parsed)

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
                    request_type="structured_chat",
                )
            raise

    def get_model_name(self) -> str:
        return self._model_name

    def get_provider_name(self) -> str:
        return "ollama"

    # ---------------------------------------
    # Private Methods
    # ---------------------------------------

    @staticmethod
    def _content_to_str(content: object) -> str:
        """Normalize LangChain content (str | list[parts]) to plain string."""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = [
                block if isinstance(block, str) else str(block.get("text", block))
                for block in content
            ]
            return "\n".join(parts)
        return str(content)
