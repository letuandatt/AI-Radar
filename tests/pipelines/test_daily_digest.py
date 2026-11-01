"""Tests for the Daily Digest pipeline (D1)."""

from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.models.knowledge_object import KnowledgeObject
from app.models.metadata import ExtractionResult
from app.pipelines.daily_digest import (
    DailyDigestPipeline,
    DigestDraft,
    DigestQueryService,
    LogChannel,
)
from app.services.digest.ranker import DigestRanker
from app.storage.knowledge.sqlite_store import SQLiteKnowledgeStore
from tests.fakes.llm import FakeLLMProvider

DAY = date(2026, 10, 6)


def make_ko(
    slug: str,
    relevance: float = 0.9,
    fetched_at: datetime | None = None,
    source_type: str = "github",
) -> KnowledgeObject:
    return KnowledgeObject(
        source_type=source_type,
        source_name="test_source",
        external_id=f"ext_{slug}",
        source_url=f"https://example.com/{slug}",
        content_hash=f"hash_{slug}",
        fetched_at=fetched_at or datetime(DAY.year, DAY.month, DAY.day, 10, 0, tzinfo=timezone.utc),
        published_at=None,
        parser_version="1.0.0",
        normalizer_version="1.0.0",
        extractor_version="1.0.0",
        title=f"Article {slug}",
        content_text=f"Content body {slug}.",
        metadata=ExtractionResult(
            summary=f"Summary of {slug}",
            topics=["ai"],
            entities=["e"],
            relevance_score=relevance,
        ),
    )


@pytest.fixture
def store(tmp_path: Path) -> SQLiteKnowledgeStore:
    return SQLiteKnowledgeStore(db_path=tmp_path / "knowledge.db")


class TestDigestQuery:
    def test_day_scope_keeps_only_window(self, store: SQLiteKnowledgeStore):
        in_window_1 = make_ko("in1", fetched_at=datetime(2026, 10, 6, 1, 0, tzinfo=timezone.utc))
        in_window_2 = make_ko("in2", fetched_at=datetime(2026, 10, 6, 23, 0, tzinfo=timezone.utc))
        before = make_ko("before", fetched_at=datetime(2026, 10, 5, 10, 0, tzinfo=timezone.utc))
        after = make_ko("after", fetched_at=datetime(2026, 10, 7, 0, 30, tzinfo=timezone.utc))
        store.save_objects([in_window_1, in_window_2, before, after])

        query = DigestQueryService(store)
        candidates = query.candidates_for_day(DAY)

        assert sorted(ko.external_id for ko in candidates) == ["ext_in1", "ext_in2"]

    def test_naive_fetched_at_normalized(self, store: SQLiteKnowledgeStore):
        naive = make_ko(
            "naive",
            fetched_at=datetime(2026, 10, 6, 5, 0),  # naive UTC
        )
        store.save_objects([naive])

        candidates = DigestQueryService(store).candidates_for_day(DAY)

        assert len(candidates) == 1


class TestDailyDigestPipeline:
    @staticmethod
    def _pipeline(
        store: SQLiteKnowledgeStore,
        provider: FakeLLMProvider | None = None,
        channel=None,
        max_items: int = 10,
    ) -> DailyDigestPipeline:
        return DailyDigestPipeline(
            sqlite_store=store,
            llm_provider=provider or FakeLLMProvider(),
            ranker=DigestRanker(),
            channel=channel,
            max_items=max_items,
        )

    def test_full_run_happy_path(self, store: SQLiteKnowledgeStore):
        store.save_objects([make_ko("a", relevance=0.9), make_ko("b", relevance=0.7)])
        provider = FakeLLMProvider(
            default_response=DigestDraft(markdown="# Digest hôm nay\n\nTổng hợp nội dung.")
        )
        channel = MagicMock()
        channel.name = "test-channel"
        channel.send.return_value = True

        result = self._pipeline(store, provider, channel).run(target_date=DAY)

        assert result.sent is True
        assert result.channel == "test-channel"
        assert result.error is None
        assert len(result.items) == 2
        assert "# Digest hôm nay" in result.markdown
        # Sources appended by code, never by the LLM
        assert "## Nguồn" in result.markdown
        assert "https://example.com/a" in result.markdown
        # LLM got the ranked insights and the DigestDraft schema
        assert len(provider.calls) == 1
        assert provider.schemas == [DigestDraft]

    def test_no_candidates_skips_llm_and_channel(self, store: SQLiteKnowledgeStore):
        provider = FakeLLMProvider()  # would raise if called
        channel = MagicMock()

        result = self._pipeline(store, provider, channel).run(target_date=DAY)

        assert result.sent is True
        assert result.markdown == ""
        assert result.items == []
        assert len(provider.calls) == 0
        channel.send.assert_not_called()

    def test_channel_failure_keeps_insights(self, store: SQLiteKnowledgeStore):
        """Plan test: delivery fails → insights NOT lost, retry re-sends only."""
        store.save_objects([make_ko("a", relevance=0.9)])
        provider = FakeLLMProvider(default_response=DigestDraft(markdown="# Digest"))
        channel = MagicMock()
        channel.name = "zalo"
        channel.send.side_effect = Exception("Zalo API down")

        result = self._pipeline(store, provider, channel).run(target_date=DAY)

        assert result.sent is False
        assert result.error == "Zalo API down"
        assert result.markdown  # digest content survives for retry
        assert len(result.items) == 1
        # A delivery-only retry re-sends the SAME markdown
        channel.send.return_value = True
        channel.send.side_effect = None
        assert channel.send(result.markdown) is True

    def test_channel_false_return_counts_as_failure(self, store: SQLiteKnowledgeStore):
        store.save_objects([make_ko("a", relevance=0.9)])
        provider = FakeLLMProvider(default_response=DigestDraft(markdown="# Digest"))
        channel = MagicMock()
        channel.name = "test"
        channel.send.return_value = False

        result = self._pipeline(store, provider, channel).run(target_date=DAY)

        assert result.sent is False
        assert result.error is not None

    def test_max_items_caps_selection(self, store: SQLiteKnowledgeStore):
        objects = [make_ko(f"k{i}", relevance=0.5 + i * 0.05) for i in range(5)]
        store.save_objects(objects)
        provider = FakeLLMProvider(default_response=DigestDraft(markdown="# Digest"))

        result = self._pipeline(store, provider, max_items=2).run(target_date=DAY)

        assert len(result.items) == 2
        # The two highest-ranked insights win
        scores = [item.score for item in result.items]
        assert scores == sorted(scores, reverse=True)

    def test_log_channel_delivers(self, caplog):
        channel = LogChannel()
        assert channel.send("# Digest") is True
        assert channel.name == "log"
