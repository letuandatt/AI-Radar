"""LLM Provider Chain with fallback logic."""

from typing import TypeVar

from pydantic import BaseModel

from app.core.circuit_breaker import CircuitBreakerOpenError
from app.core.logger import get_logger
from app.integrations.llm.provider import LLMProvider

logger = get_logger(__name__)

T = TypeVar("T", bound=BaseModel)


class LLMProviderChain:
    """
    Chain of LLM providers with fallback.

    Tries providers in order. If one fails (CircuitBreaker open or transient error),
    moves to the next provider.

    Args:
        providers: List of LLM providers in priority order.
    """

    def __init__(self, providers: list[LLMProvider]) -> None:
        if not providers:
            raise ValueError("At least one provider is required")
        self._providers = providers

    def chat(self, prompt: str, **kwargs: object) -> str:
        """Try each provider in order until one succeeds."""
        last_error = None

        for provider in self._providers:
            try:
                return provider.chat(prompt, **kwargs)
            except CircuitBreakerOpenError as e:
                logger.warning(
                    "Provider %s circuit breaker open, trying next provider",
                    provider.get_provider_name(),
                )
                last_error = e
                continue
            except Exception as e:
                logger.warning(
                    "Provider %s failed: %s, trying next provider",
                    provider.get_provider_name(),
                    str(e),
                )
                last_error = e  # type: ignore[assignment]
                continue

        # All providers failed
        if last_error:
            raise last_error
        raise RuntimeError("All providers failed")

    def structured_chat(self, prompt: str, schema: type[T]) -> T:
        """Try each provider in order until one succeeds."""
        last_error = None

        for provider in self._providers:
            try:
                return provider.structured_chat(prompt, schema)
            except CircuitBreakerOpenError as e:
                logger.warning(
                    "Provider %s circuit breaker open, trying next provider",
                    provider.get_provider_name(),
                )
                last_error = e
                continue
            except Exception as e:
                logger.warning(
                    "Provider %s failed: %s, trying next provider",
                    provider.get_provider_name(),
                    str(e),
                )
                last_error = e  # type: ignore[assignment]
                continue

        # All providers failed
        if last_error:
            raise last_error
        raise RuntimeError("All providers failed")

    def get_model_name(self) -> str:
        """Get model name of primary provider."""
        return self._providers[0].get_model_name()

    def get_provider_name(self) -> str:
        """Get provider name of primary provider."""
        return self._providers[0].get_provider_name()
