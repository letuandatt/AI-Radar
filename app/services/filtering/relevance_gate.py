"""Deterministic relevance gate — pre-filter BEFORE LLM extraction (C1).

Cheap signals only, in this order:
1. min_content_length  — articles too short to be worth extracting
2. freshness           — articles older than a configurable window
3. topic keywords      — title/content keyword match (FLAG-OFF by default:
                         enable only once kept/filtered metrics exist, since
                         keyword filtering silently drops good articles)

The gate never uses an LLM. ``relevance_score`` produced BY the LLM cannot
be used here — it only exists after extraction (that ordering is the whole
point of the gate).
"""

from dataclasses import dataclass
from datetime import datetime, timezone

from app.core.logger import get_logger
from app.models.normalized_article import NormalizedArticle

logger = get_logger(__name__)


@dataclass(frozen=True)
class FilteredArticle:
    """One rejected article with the reason (observability requirement)."""

    url: str
    title: str
    reason: str


class RelevanceGate:
    """Filters normalized articles before they reach LLM extraction.

    Args:
        min_content_length: Minimum content length in chars (0 disables).
        max_article_age_days: Reject articles older than this (None disables).
        topic_keywords: Require at least one keyword in title/content
            (empty list disables — default, until metrics exist).
    """

    def __init__(
        self,
        min_content_length: int = 50,
        max_article_age_days: float | None = None,
        topic_keywords: list[str] | None = None,
    ) -> None:
        self._min_content_length = min_content_length
        self._max_article_age_days = max_article_age_days
        self._topic_keywords = [k.lower() for k in (topic_keywords or [])]

    def filter(
        self,
        articles: list[NormalizedArticle],
        now: datetime | None = None,
    ) -> tuple[list[NormalizedArticle], list[FilteredArticle]]:
        """Partition articles into (kept, filtered-with-reasons).

        Args:
            articles: Normalized candidates (post clean/normalize).
            now: Injected clock for testability; defaults to UTC now.

        Returns:
            Tuple of kept articles and filtered articles, each with reason.
        """
        current_time = now or datetime.now(timezone.utc)
        kept: list[NormalizedArticle] = []
        filtered: list[FilteredArticle] = []

        for article in articles:
            reason = self._rejection_reason(article, current_time)
            if reason is None:
                kept.append(article)
            else:
                filtered.append(FilteredArticle(article.url, article.title, reason))
                logger.info("Gate filtered %s: %s", article.url, reason)

        logger.info(
            "Relevance gate: kept=%d filtered=%d (input=%d)",
            len(kept),
            len(filtered),
            len(articles),
        )
        return kept, filtered

    def _rejection_reason(self, article: NormalizedArticle, now: datetime) -> str | None:
        """Return the rejection reason for the article, or None to keep it."""
        content_length = len(article.content.strip())
        if content_length < self._min_content_length:
            return f"content too short: {content_length} < min {self._min_content_length}"

        if self._max_article_age_days is not None:
            age_days = self._age_days(article, now)
            if age_days is not None and age_days > self._max_article_age_days:
                return f"stale: {age_days:.1f}d > max {self._max_article_age_days}d"

        if self._topic_keywords:
            haystack = f"{article.title}\n{article.content}".lower()
            if not any(keyword in haystack for keyword in self._topic_keywords):
                return "no topic keyword match"

        return None

    @staticmethod
    def _age_days(article: NormalizedArticle, now: datetime) -> float | None:
        """Article age in days, or None when fetched_at is unknown."""
        fetched_at = article.fetched_at
        if fetched_at is None:
            return None
        if fetched_at.tzinfo is None:
            fetched_at = fetched_at.replace(tzinfo=timezone.utc)
        return (now - fetched_at).total_seconds() / 86400
