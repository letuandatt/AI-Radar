"""Tests for the digest ranking service (C3)."""

from datetime import datetime, timedelta, timezone

from app.models.knowledge_object import KnowledgeObject
from app.models.metadata import ExtractionResult
from app.services.digest.ranker import DigestRanker

NOW = datetime(2026, 10, 7, 12, 0, tzinfo=timezone.utc)


def make_ko(
    slug: str,
    relevance: float = 0.8,
    fetched_at: datetime | None = NOW - timedelta(hours=1),
    source_type: str = "github",
) -> KnowledgeObject:
    return KnowledgeObject(
        source_type=source_type,
        source_name="test",
        external_id=f"ext_{slug}",
        source_url=f"https://example.com/{slug}",
        content_hash=f"hash_{slug}",
        fetched_at=fetched_at or (NOW - timedelta(days=30)),
        published_at=None,
        parser_version="1.0.0",
        normalizer_version="1.0.0",
        extractor_version="1.0.0",
        title=f"Article {slug}",
        content_text=f"Content {slug}",
        metadata=ExtractionResult(
            summary=f"Summary {slug}",
            topics=["ai"],
            entities=["e"],
            relevance_score=relevance,
        ),
    )


class TestRanking:
    def test_orders_by_relevance_first(self):
        ranker = DigestRanker()
        low = make_ko("low", relevance=0.4)
        high = make_ko("high", relevance=0.95)

        ranked = ranker.rank([low, high], now=NOW)

        assert [item.knowledge_object.external_id for item in ranked] == ["ext_high", "ext_low"]
        assert ranked[0].score > ranked[1].score

    def test_freshness_breaks_relevance_ties(self):
        ranker = DigestRanker()
        newer = make_ko("newer", relevance=0.8, fetched_at=NOW - timedelta(hours=1))
        older = make_ko("older", relevance=0.8, fetched_at=NOW - timedelta(days=3))

        ranked = ranker.rank([older, newer], now=NOW)

        assert ranked[0].knowledge_object.external_id == "ext_newer"
        assert ranked[0].freshness > ranked[1].freshness

    def test_source_priority_breaks_full_ties(self):
        ranker = DigestRanker(max_age_days=1000)  # freshness equal-ish
        github = make_ko("gh", relevance=0.8, source_type="github")
        rss = make_ko("rss", relevance=0.8, source_type="rss")

        ranked = ranker.rank([rss, github], now=NOW)

        assert ranked[0].knowledge_object.source_type == "github"
        assert ranked[0].source_priority > ranked[1].source_priority

    def test_threshold_filters_low_scores(self):
        ranker = DigestRanker(threshold=0.5)
        good = make_ko("good", relevance=0.95)
        weak = make_ko("weak", relevance=0.1, fetched_at=NOW - timedelta(days=30))

        ranked = ranker.rank([good, weak], now=NOW)

        assert [item.knowledge_object.external_id for item in ranked] == ["ext_good"]

    def test_empty_candidates(self):
        assert DigestRanker().rank([], now=NOW) == []

    def test_unknown_source_type_gets_neutral_priority(self):
        ranker = DigestRanker()
        item = ranker._score(make_ko("x", source_type="podcast"), NOW)

        assert item.source_priority == 0.5

    def test_naive_fetched_at_treated_as_utc(self):
        ranker = DigestRanker(max_age_days=7)
        naive_fresh = make_ko(
            "naive",
            fetched_at=(NOW - timedelta(hours=1)).replace(tzinfo=None),
        )

        item = ranker._score(naive_fresh, NOW)

        assert item.freshness > 0.9
