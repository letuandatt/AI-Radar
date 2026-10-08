"""Tests for CostTracker."""

from datetime import date, timedelta

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
        tomorrow = date.today() + timedelta(days=1)
        monkeypatch.setattr(
            "app.core.cost_tracker.date",
            type("MockDate", (), {"today": staticmethod(lambda: tomorrow)}),
        )

        assert tracker.get_current_cost() == 0.0


# ==============================================================================
# Pre-Request Budget Check Tests (B6)
# ==============================================================================


class TestCheckBudget:
    """check_budget must decide BEFORE the request runs (estimate -> check)."""

    def test_denied_when_estimate_exceeds_remaining_budget(self):
        tracker = CostTracker(daily_budget_usd=0.001)

        decision = tracker.check_budget(estimated_cost=0.05)

        assert decision.allowed is False
        assert "exceeds budget" in decision.reason

    def test_allowed_when_within_budget(self):
        tracker = CostTracker(daily_budget_usd=10.0)

        decision = tracker.check_budget(estimated_cost=0.05)

        assert decision.allowed is True
        assert decision.reason == ""

    def test_allowed_exactly_at_budget_edge(self):
        tracker = CostTracker(daily_budget_usd=0.05)

        assert tracker.check_budget(estimated_cost=0.05).allowed is True

    def test_token_limit_denies(self):
        tracker = CostTracker(daily_budget_usd=10.0, daily_token_limit=1000)
        tracker.track("groq", "m", 800, 100, 0.0)  # 900 tokens used

        decision = tracker.check_budget(estimated_cost=0.0, estimated_tokens=200)

        assert decision.allowed is False
        assert "daily limit" in decision.reason

    def test_request_limit_denies(self):
        tracker = CostTracker(daily_budget_usd=10.0, daily_request_limit=2)
        tracker.track("groq", "m", 1, 1, 0.0)
        tracker.track("groq", "m", 1, 1, 0.0)

        decision = tracker.check_budget(estimated_cost=0.0)

        assert decision.allowed is False
        assert "requests" in decision.reason

    def test_track_reconciles_counters_for_next_check(self):
        """After real usage, the next pre-check projects on the real numbers."""
        tracker = CostTracker(daily_budget_usd=0.10)
        tracker.track("groq", "m", 1000, 500, 0.08)  # real cost $0.08

        assert tracker.get_current_cost() == pytest.approx(0.08)
        assert tracker.tokens_today == 1500
        assert tracker.requests_today == 1

        # $0.08 spent + $0.05 estimate > $0.10 → denied now
        assert tracker.check_budget(estimated_cost=0.05).allowed is False
        # Smaller estimate still fits
        assert tracker.check_budget(estimated_cost=0.01).allowed is True


def test_budget_alert_at_80_percent_once_per_day(caplog, monkeypatch):
    caplog.set_level("WARNING")
    tracker = CostTracker(daily_budget_usd=10.0, alert_percent=0.8)

    def alert_count():
        return sum("LLM budget alert:" in message for message in caplog.messages)

    tracker.track("groq", "test-model", 100, 50, 7.0)
    assert alert_count() == 0

    tracker.track("groq", "test-model", 100, 50, 1.0)
    assert alert_count() == 1

    tracker.track("groq", "test-model", 100, 50, 0.5)
    assert alert_count() == 1

    tomorrow = date.today() + timedelta(days=1)
    monkeypatch.setattr(
        "app.core.cost_tracker.date",
        type("MockDate", (), {"today": staticmethod(lambda: tomorrow)}),
    )

    assert tracker.snapshot() == {
        "requests_today": 0,
        "tokens_today": 0,
        "current_cost": 0.0,
    }
    assert tracker.alert_sent is False

    tracker.track("groq", "test-model", 100, 50, 8.0)
    assert alert_count() == 2
