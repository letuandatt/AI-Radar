"""LLM Provider Chain with fallback logic."""

from typing import TYPE_CHECKING, TypeVar

from pydantic import BaseModel

from app.core.circuit_breaker import CircuitBreakerOpenError
from app.core.exceptions import BudgetExceededError, RateLimitWaitTimeoutError, TransientLLMError
from app.core.logger import get_logger
from app.core.rate_limiter import TokenBucket
from app.integrations.llm.provider import LLMProvider

if TYPE_CHECKING:
    from app.core.cost_tracker import CostTracker

logger = get_logger(__name__)

T = TypeVar("T", bound=BaseModel)

# Only provider-level failures justify fallback: an open circuit or a
# transient error (429/timeout/5xx). App bugs (schema, serialization, state)
# raise immediately — falling back would mask them (Wiring & Fix Plan B5).
_FALLBACK_ERRORS = (CircuitBreakerOpenError, TransientLLMError)


class LLMProviderChain:
    """
    Chain of LLM providers with fallback.

    Tries providers in order. If one fails with a provider-level failure
    (circuit breaker open or transient error), moves to the next provider.
    Any other exception is a bug and propagates immediately.

    Before each provider call the chain runs the pre-request budget check
    (B6): estimate → check. A denied provider is skipped and the next one
    (typically free Ollama) is tried; if every provider is denied, the
    BudgetExceededError propagates — no LLM call happens.

    Args:
        providers: List of LLM providers in priority order.
        rate_limiter: Optional shared TokenBucket applied before every provider
            call. The limit belongs at the chain (gateway) level, not per
            provider — a Groq→Ollama fallback must not be throttled twice.
        rate_limit_wait_timeout: Max seconds to wait for a token before
            raising RateLimitWaitTimeoutError (no provider is called).
        cost_tracker: Optional shared CostTracker for pre-request budget
            enforcement. None disables the check (tests).
    """

    def __init__(
        self,
        providers: list[LLMProvider],
        rate_limiter: TokenBucket | None = None,
        rate_limit_wait_timeout: float = 30.0,
        cost_tracker: "CostTracker | None" = None,
    ) -> None:
        if not providers:
            raise ValueError("At least one provider is required")
        self._providers = providers
        self._rate_limiter = rate_limiter
        self._rate_limit_wait_timeout = rate_limit_wait_timeout
        self._cost_tracker = cost_tracker

    def _acquire(self) -> None:
        """Block until a rate limiter token is available or time out."""
        if self._rate_limiter is None:
            return
        if not self._rate_limiter.wait_and_acquire(timeout=self._rate_limit_wait_timeout):
            raise RateLimitWaitTimeoutError(
                f"Rate limiter wait exceeded {self._rate_limit_wait_timeout}s"
            )

    def _budget_allows(self, provider: LLMProvider, prompt: str) -> bool:
        """Pre-request budget check: estimate → check (B6). Never blocks."""
        if self._cost_tracker is None:
            return True
        decision = self._cost_tracker.check_budget(provider.estimate_cost(prompt))
        if not decision.allowed:
            logger.warning(
                "Budget denied for provider %s: %s",
                provider.get_provider_name(),
                decision.reason,
            )
        return decision.allowed

    def chat(self, prompt: str, **kwargs: object) -> str:
        """Try each provider in order until one succeeds."""
        last_error: BaseException | None = None

        for provider in self._providers:
            self._acquire()
            if not self._budget_allows(provider, prompt):
                last_error = BudgetExceededError(
                    f"budget denied for {provider.get_provider_name()}"
                )
                continue
            try:
                return provider.chat(prompt, **kwargs)
            except _FALLBACK_ERRORS as e:
                logger.warning(
                    "Provider %s failed (%s), trying next provider",
                    provider.get_provider_name(),
                    type(e).__name__,
                )
                last_error = e
                continue

        # All providers failed
        if last_error:
            raise last_error
        raise RuntimeError("All providers failed")

    def structured_chat(self, prompt: str, schema: type[T]) -> T:
        """Try each provider in order until one succeeds."""
        last_error: BaseException | None = None

        for provider in self._providers:
            self._acquire()
            if not self._budget_allows(provider, prompt):
                last_error = BudgetExceededError(
                    f"budget denied for {provider.get_provider_name()}"
                )
                continue
            try:
                return provider.structured_chat(prompt, schema)
            except _FALLBACK_ERRORS as e:
                logger.warning(
                    "Provider %s failed (%s), trying next provider",
                    provider.get_provider_name(),
                    type(e).__name__,
                )
                last_error = e
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

    @property
    def cost_tracker(self) -> "CostTracker | None":
        """The shared CostTracker (P1.9: entrypoints snapshot it per run)."""
        return self._cost_tracker

    def estimate_cost(self, prompt: str) -> float:
        """Estimate from the primary provider (chain-as-provider view)."""
        return self._providers[0].estimate_cost(prompt)
