"""Digest ranking (C3): composite score applied AFTER LLM extraction.

``relevance_score`` is produced BY the LLM — it may only be used AFTER
extraction; using it as a pre-filter would be circular logic (Wiring &
Fix Plan C3). The ranker combines it with cheap deterministic signals:

- freshness: linear decay from 1.0 (brand new) to 0.0 at max_age_days
- source_priority: per source_type, defaults github > huggingface > rss
- relevance: the extractor's own 0.0-1.0 score, weighted heaviest

Items scoring below ``threshold`` are dropped from digest candidates.
"""

from dataclasses import dataclass
from datetime import datetime, timezone

from app.core.logger import get_logger
from app.models.knowledge_object import KnowledgeObject

logger = get_logger(__name__)

DEFAULT_WEIGHTS = {"relevance": 0.6, "freshness": 0.25, "source": 0.15}
DEFAULT_SOURCE_PRIORITIES = {"github": 1.0, "huggingface": 0.9, "rss": 0.7}
DEFAULT_MAX_AGE_DAYS = 7.0
DEFAULT_THRESHOLD = 0.35


@dataclass(frozen=True)
class RankedDigestItem:
    """One digest candidate with its composite score components."""

    knowledge_object: KnowledgeObject
    score: float
    relevance: float
    freshness: float
    source_priority: float


class DigestRanker:
    """Ranks KnowledgeObjects for the daily digest.

    Args:
        weights: Signal weights, defaults relevance 0.6 / freshness 0.25 /
            source 0.15 (relevance dominates; the rest break ties).
        source_priorities: Per source_type in [0, 1]; unknown types get 0.5.
        max_age_days: Freshness reaches 0.0 at this age.
        threshold: Minimum composite score to enter the digest.
    """

    def __init__(
        self,
        weights: dict[str, float] | None = None,
        source_priorities: dict[str, float] | None = None,
        max_age_days: float = DEFAULT_MAX_AGE_DAYS,
        threshold: float = DEFAULT_THRESHOLD,
    ) -> None:
        self._weights = {**DEFAULT_WEIGHTS, **(weights or {})}
        self._source_priorities = {
            **DEFAULT_SOURCE_PRIORITIES,
            **(source_priorities or {}),
        }
        self._max_age_days = max_age_days
        self._threshold = threshold

    def rank(
        self,
        candidates: list[KnowledgeObject],
        now: datetime | None = None,
    ) -> list[RankedDigestItem]:
        """Score, threshold-filter, and sort candidates (best first).

        Args:
            candidates: KnowledgeObjects extracted for the digest window.
            now: Injected clock for testability; defaults to UTC now.

        Returns:
            Ranked items above the threshold, best first.
        """
        current_time = now or datetime.now(timezone.utc)
        scored = [self._score(ko, current_time) for ko in candidates]
        ranked = [item for item in scored if item.score >= self._threshold]
        ranked.sort(key=lambda item: item.score, reverse=True)
        logger.info(
            "Digest ranking: %d/%d candidates above threshold %.2f",
            len(ranked),
            len(candidates),
            self._threshold,
        )
        return ranked

    def _score(self, ko: KnowledgeObject, now: datetime) -> RankedDigestItem:
        relevance = self._relevance(ko)
        freshness = self._freshness(ko, now)
        source_priority = self._source_priorities.get(ko.source_type, 0.5)
        score = (
            self._weights["relevance"] * relevance
            + self._weights["freshness"] * freshness
            + self._weights["source"] * source_priority
        )
        return RankedDigestItem(
            knowledge_object=ko,
            score=round(score, 4),
            relevance=relevance,
            freshness=round(freshness, 4),
            source_priority=source_priority,
        )

    @staticmethod
    def _relevance(ko: KnowledgeObject) -> float:
        """Extractor relevance_score clamped to [0, 1]; 0.0 when missing."""
        try:
            score = float(ko.metadata.relevance_score)
        except (AttributeError, TypeError, ValueError):
            return 0.0
        return min(1.0, max(0.0, score))

    def _freshness(self, ko: KnowledgeObject, now: datetime) -> float:
        """1.0 brand-new, decaying linearly to 0.0 at max_age_days."""
        fetched_at = ko.fetched_at
        if fetched_at is None:
            return 0.0
        if fetched_at.tzinfo is None:
            fetched_at = fetched_at.replace(tzinfo=timezone.utc)
        age_days = (now - fetched_at).total_seconds() / 86400
        if age_days <= 0:
            return 1.0
        return max(0.0, 1.0 - age_days / self._max_age_days)
