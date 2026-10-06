"""LLM Cost Tracking and Budget Guard (GAP-015)."""

import threading
from dataclasses import dataclass
from datetime import date

from app.core.logger import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class BudgetDecision:
    """Outcome of a pre-request budget check (B6).

    Attributes:
        allowed: Whether the request may proceed.
        reason: Human-readable denial reason (empty when allowed).
    """

    allowed: bool
    reason: str = ""


class CostTracker:
    """Tracks LLM usage cost and enforces daily budget BEFORE requests.

    Pre-request enforcement (B6): ``check_budget`` must be called with the
    estimated cost BEFORE invoking the LLM; ``track`` records the real usage
    afterwards (reconciliation). Estimated checks on real numbers only make
    sense because ``track`` receives true token counts.

    Args:
        daily_budget_usd: Maximum daily spend in USD.
        alert_percent: Percentage of budget at which to send alert (0.0-1.0).
        daily_token_limit: Optional max tokens per day (None disables).
        daily_request_limit: Optional max requests per day (None disables).
    """

    def __init__(
        self,
        daily_budget_usd: float = 10.0,
        alert_percent: float = 0.8,
        daily_token_limit: int | None = None,
        daily_request_limit: int | None = None,
    ) -> None:
        self.daily_budget_usd = daily_budget_usd
        self.alert_percent = alert_percent
        self.daily_token_limit = daily_token_limit
        self.daily_request_limit = daily_request_limit
        self.current_cost = 0.0
        self.tokens_today = 0
        self.requests_today = 0
        self.last_reset_date = date.today()
        self.lock = threading.Lock()
        self.alert_sent = False

    def _check_reset(self) -> None:
        """Reset cost tracker if day has changed."""
        today = date.today()
        if today > self.last_reset_date:
            logger.info("CostTracker: Daily reset ($%.4f -> $0.00)", self.current_cost)
            self.current_cost = 0.0
            self.tokens_today = 0
            self.requests_today = 0
            self.last_reset_date = today
            self.alert_sent = False

    def check_budget(self, estimated_cost: float, estimated_tokens: int = 0) -> BudgetDecision:
        """Decide whether a request may proceed BEFORE it runs.

        Args:
            estimated_cost: Estimated USD cost of the request.
            estimated_tokens: Estimated total tokens of the request.

        Returns:
            BudgetDecision — allowed=False means the caller must NOT call
            the LLM (fall back to a free provider or skip the item).
        """
        with self.lock:
            self._check_reset()

            projected_cost = self.current_cost + max(0.0, estimated_cost)
            if projected_cost > self.daily_budget_usd:
                reason = (
                    f"cost ${self.current_cost:.4f} + est ${max(0.0, estimated_cost):.4f} "
                    f"exceeds budget ${self.daily_budget_usd:.2f}"
                )
                logger.warning("Budget check denied: %s", reason)
                return BudgetDecision(allowed=False, reason=reason)

            if (
                self.daily_token_limit is not None
                and self.tokens_today + max(0, estimated_tokens) > self.daily_token_limit
            ):
                reason = (
                    f"tokens {self.tokens_today} + est {max(0, estimated_tokens)} "
                    f"exceeds daily limit {self.daily_token_limit}"
                )
                logger.warning("Budget check denied: %s", reason)
                return BudgetDecision(allowed=False, reason=reason)

            if (
                self.daily_request_limit is not None
                and self.requests_today + 1 > self.daily_request_limit
            ):
                reason = (
                    f"requests {self.requests_today} + 1 "
                    f"exceeds daily limit {self.daily_request_limit}"
                )
                logger.warning("Budget check denied: %s", reason)
                return BudgetDecision(allowed=False, reason=reason)

            return BudgetDecision(allowed=True)

    def track(
        self,
        provider: str,
        model: str,
        tokens_in: int,
        tokens_out: int,
        cost_usd: float,
    ) -> None:
        """
        Track an LLM call cost.

        Args:
            provider: Provider name (e.g., "ollama", "groq").
            model: Model name.
            tokens_in: Input tokens.
            tokens_out: Output tokens.
            cost_usd: Cost in USD.

        Raises:
            BudgetExceededError: If daily budget is exceeded.
        """
        from app.core.exceptions import BudgetExceededError

        with self.lock:
            self._check_reset()
            self.current_cost += cost_usd
            self.tokens_today += tokens_in + tokens_out
            self.requests_today += 1

            if self.current_cost >= self.daily_budget_usd:
                logger.error(
                    "LLM budget exceeded: $%.4f / $%.4f (provider=%s, model=%s)",
                    self.current_cost,
                    self.daily_budget_usd,
                    provider,
                    model,
                )
                raise BudgetExceededError(
                    f"Daily LLM budget exceeded: ${self.current_cost:.4f} "
                    f"/ ${self.daily_budget_usd:.4f}"
                )

            daily_alert_percent = self.daily_budget_usd * self.alert_percent

            if not self.alert_sent and self.current_cost >= daily_alert_percent:
                logger.warning(
                    "LLM budget alert: $%.4f / $%.4f (%.0f%%) (provider=%s, model=%s)",
                    self.current_cost,
                    self.daily_budget_usd,
                    (self.current_cost / self.daily_budget_usd) * 100,
                    provider,
                    model,
                )
                self.alert_sent = True

    def get_current_cost(self) -> float:
        """Get current daily cost."""
        with self.lock:
            self._check_reset()
            return self.current_cost

    def get_remaining_budget(self) -> float:
        """Get remaining daily budget."""
        with self.lock:
            self._check_reset()
            return max(0.0, self.daily_budget_usd - self.current_cost)
