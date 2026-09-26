"""Tests for CostTracker."""

from datetime import date

import pytest

from app.core.cost_tracker import CostTracker
from app.core.exceptions import BudgetExceededError


class TestCostTracker:
    def test_track_cost(self):
        tracker = CostTracker(daily_budget_usd=10.0)
        tracker.track("ollama", "qwen3:4b", 100, 50, 0.01)
        assert tracker.get_current_cost() == 0.01

    def test_budget_exceeded(self):
        tracker = CostTracker(daily_budget_usd=1.0)
        tracker.track("groq", "llama-3.1-70b", 1000, 500, 0.5)

        with pytest.raises(BudgetExceededError):
            tracker.track("groq", "llama-3.1-70b", 1000, 500, 0.6)

    def test_remaining_budget(self):
        tracker = CostTracker(daily_budget_usd=10.0)
        tracker.track("ollama", "qwen3:4b", 100, 50, 3.0)
        assert tracker.get_remaining_budget() == 7.0

    def test_daily_reset(self, monkeypatch):
        tracker = CostTracker(daily_budget_usd=10.0)
        tracker.track("ollama", "qwen3:4b", 100, 50, 5.0)
        assert tracker.get_current_cost() == 5.0

        # Simulate day change
        tomorrow = date.today()
        tomorrow = tomorrow.replace(day=tomorrow.day + 1)
        monkeypatch.setattr(
            "app.core.cost_tracker.date",
            type("MockDate", (), {"today": staticmethod(lambda: tomorrow)}),
        )

        assert tracker.get_current_cost() == 0.0
