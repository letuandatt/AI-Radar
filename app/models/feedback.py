"""Deterministic feedback policy shared by services and persistence."""

from math import isfinite
from typing import Literal

FeedbackRating = Literal["useful", "not_useful"]
FEEDBACK_STEP = 0.1


def adjusted_importance(base: float, rating: FeedbackRating | None) -> float:
    """Apply one bounded adjustment to the original score, never to a previous adjustment."""
    if not isfinite(base) or not 0 <= base <= 1:
        raise ValueError("Base importance must be finite and between zero and one")
    if rating not in {None, "useful", "not_useful"}:
        raise ValueError("Unsupported feedback rating")
    delta = FEEDBACK_STEP if rating == "useful" else -FEEDBACK_STEP if rating else 0.0
    return min(1.0, max(0.0, base + delta))
