"""Tests for the deterministic RelevanceGate (C1)."""

from datetime import datetime, timedelta, timezone

from app.models.normalized_article import NormalizedArticle
from app.services.filtering.relevance_gate import RelevanceGate

NOW = datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc)


def make_article(
    article_id: str = "hash_1",
    title: str = "LLM agents are evolving",
    content: str = "Long enough content about llm agents and retrieval.",
    url: str = "https://example.com/a1",
    fetched_at: datetime | None = NOW,
) -> NormalizedArticle:
    return NormalizedArticle(
        article_id=article_id,
        title=title,
        content=content,
        url=url,
        source_name="test",
        source_type="rss",
        author=None,
        published_date=None,
        fetched_at=fetched_at,
        raw_content_hash=article_id,
    )


class TestLengthRule:
    def test_short_content_is_filtered_with_reason(self):
        gate = RelevanceGate(min_content_length=50)
        short = make_article(article_id="s", content="tiny", url="https://x.com/s")
        kept, filtered = gate.filter([short])

        assert kept == []
        assert len(filtered) == 1
        assert "content too short" in filtered[0].reason
        assert filtered[0].url == "https://x.com/s"

    def test_long_content_is_kept(self):
        gate = RelevanceGate(min_content_length=10)
        kept, filtered = gate.filter([make_article()])

        assert len(kept) == 1
        assert filtered == []


class TestFreshnessRule:
    def test_stale_article_is_filtered(self):
        gate = RelevanceGate(min_content_length=0, max_article_age_days=7)
        old = make_article(fetched_at=NOW - timedelta(days=10), url="https://x.com/old")
        fresh = make_article(fetched_at=NOW - timedelta(days=1), url="https://x.com/new")

        kept, filtered = gate.filter([old, fresh], now=NOW)

        assert [a.url for a in kept] == ["https://x.com/new"]
        assert len(filtered) == 1
        assert "stale" in filtered[0].reason

    def test_missing_fetched_at_is_kept(self):
        gate = RelevanceGate(min_content_length=0, max_article_age_days=7)
        kept, filtered = gate.filter([make_article(fetched_at=None)])

        assert len(kept) == 1
        assert filtered == []

    def test_naive_fetched_at_treated_as_utc(self):
        gate = RelevanceGate(min_content_length=0, max_article_age_days=7)
        naive_old = make_article(fetched_at=(NOW - timedelta(days=10)).replace(tzinfo=None))

        kept, filtered = gate.filter([naive_old], now=NOW)

        assert kept == []
        assert len(filtered) == 1


class TestTopicKeywordsRule:
    def test_keyword_mismatch_is_filtered(self):
        gate = RelevanceGate(min_content_length=0, topic_keywords=["llm", "rag"])
        on_topic = make_article(article_id="on", url="https://x.com/on")
        off_topic = make_article(
            article_id="off",
            title="Recipe for sourdough bread",
            content="Flour, water, salt and patience.",
            url="https://x.com/off",
        )

        kept, filtered = gate.filter([on_topic, off_topic])

        assert [a.url for a in kept] == ["https://x.com/on"]
        assert len(filtered) == 1
        assert "no topic keyword match" in filtered[0].reason

    def test_keywords_empty_means_rule_off(self):
        gate = RelevanceGate(min_content_length=0, topic_keywords=[])
        off_topic = make_article(
            title="Recipe for sourdough bread",
            content="Flour, water, salt and patience.",
        )

        kept, filtered = gate.filter([off_topic])

        assert len(kept) == 1
        assert filtered == []


class TestAllRulesDisabled:
    def test_no_rules_keep_everything(self):
        """Plan test: gate config tắt hết rule → kept = 100%."""
        gate = RelevanceGate(
            min_content_length=0,
            max_article_age_days=None,
            topic_keywords=[],
        )
        articles = [make_article(article_id=f"h{i}", url=f"https://x.com/{i}") for i in range(10)]

        kept, filtered = gate.filter(articles)

        assert len(kept) == 10
        assert filtered == []


class TestMixedBatch:
    def test_mixed_batch_reasons_are_accurate(self):
        """Plan test shape: filtered articles each carry their exact reason."""
        gate = RelevanceGate(
            min_content_length=50,
            max_article_age_days=7,
            topic_keywords=["llm"],
        )
        articles = [
            make_article(article_id="ok1", url="https://x.com/ok1"),
            make_article(article_id="ok2", url="https://x.com/ok2"),
            make_article(article_id="short", content="tiny", url="https://x.com/short"),
            make_article(
                article_id="stale",
                url="https://x.com/stale",
                fetched_at=NOW - timedelta(days=30),
            ),
            make_article(
                article_id="off",
                title="Gardening tips for autumn",
                content="Water the plants regularly and prune the roses before the frost arrives.",
                url="https://x.com/off",
            ),
        ]

        kept, filtered = gate.filter(articles, now=NOW)

        assert [a.url for a in kept] == ["https://x.com/ok1", "https://x.com/ok2"]
        reasons = {f.url: f.reason for f in filtered}
        assert "content too short" in reasons["https://x.com/short"]
        assert "stale" in reasons["https://x.com/stale"]
        assert "no topic keyword match" in reasons["https://x.com/off"]
