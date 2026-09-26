"""LLM Cost Tracking and Budget Guard (GAP-015)."""

import threading
from datetime import date

from app.core.logger import get_logger

logger = get_logger(__name__)


class CostTracker:
    """
    Tracks LLM usage cost and enforces daily budget.

    Args:
        daily_budget_usd: Maximum daily spend in USD.
        alert_percent: Percentage of budget at which to send alert (0.0-1.0).
    """

    def __init__(
        self,
        daily_budget_usd: float = 10.0,
        alert_percent: float = 0.8,
    ) -> None:
        self.daily_budget_usd = daily_budget_usd
        self.alert_percent = alert_percent
        self.current_cost = 0.0
        self.last_reset_date = date.today()
        self.lock = threading.Lock()
        self.alert_sent = False

    def _check_reset(self) -> None:
        """Reset cost tracker if day has changed."""
        today = date.today()
        if today > self.last_reset_date:
            logger.info("CostTracker: Daily reset ($%.4f -> $0.00)", self.current_cost)
            self.current_cost = 0.0
            self.last_reset_date = today
            self.alert_sent = False

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
