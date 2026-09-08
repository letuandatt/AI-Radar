"""Unit tests for ContextBuilder (CCH)."""

from datetime import datetime, timezone

import pytest

from app.core.utils import compute_text_hash
from app.models.knowledge_object import KnowledgeObject
from app.models.metadata import ExtractionResult
from app.services.embedding.context_builder import ContextBuilder


@pytest.fixture
def builder() -> ContextBuilder:
    return ContextBuilder()


@pytest.fixture
def sample_ko() -> KnowledgeObject:
    metadata = ExtractionResult(
        summary="Test summary",
        topics=["AI", "Machine Learning", "NLP"],
        entities=["OpenAI"],
        relevance_score=0.9,
    )
    return KnowledgeObject(
        source_type="rss",
        source_name="techcrunch",
        external_id="ext_001",
        source_url="https://example.com/article",
        content_hash=compute_text_hash("Test content"),
        fetched_at=datetime(2025, 1, 2, tzinfo=timezone.utc),
        published_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        title="Test Title",
        content_text="Test content for embedding.",
        metadata=metadata,
    )


class TestBuildHeader:
    """Tests for build_header method."""

    def test_header_format(self, builder: ContextBuilder, sample_ko: KnowledgeObject) -> None:
        """Header has correct format."""
        header = builder.build_header(sample_ko)

        assert header.startswith("[Source: techcrunch|")
        assert "Type: rss|" in header
        assert "Date: 2025-01-01|" in header
        assert "Topics:" in header
        assert header.endswith("]")

    def test_header_includes_topics(
        self, builder: ContextBuilder, sample_ko: KnowledgeObject
    ) -> None:
        """Header includes topics from metadata."""
        header = builder.build_header(sample_ko)

        assert "AI" in header
        assert "Machine Learning" in header

    def test_header_truncates_long_metadata(self, builder: ContextBuilder) -> None:
        """Header is truncated if too long."""
        metadata = ExtractionResult(
            summary="Summary",
            topics=["Topic" + str(i) for i in range(50)],  # Many topics
            entities=["Entity"],
            relevance_score=0.9,
        )
        ko = KnowledgeObject(
            source_type="rss",
            source_name="very_long_source_name_that_exceeds_limit",
            external_id="ext_001",
            source_url="https://example.com",
            content_hash="hash",
            fetched_at=datetime.now(timezone.utc),
            published_at=datetime.now(timezone.utc),
            title="Title",
            content_text="Content",
            metadata=metadata,
        )

        header = builder.build_header(ko)
        assert len(header) <= 200

    def test_header_handles_none_published_at(self, builder: ContextBuilder) -> None:
        """Header handles None published_at."""
        metadata = ExtractionResult(
            summary="Summary",
            topics=["AI"],
            entities=["Entity"],
            relevance_score=0.9,
        )
        ko = KnowledgeObject(
            source_type="rss",
            source_name="source",
            external_id="ext_001",
            source_url="https://example.com",
            content_hash="hash",
            fetched_at=datetime.now(timezone.utc),
            published_at=None,
            title="Title",
            content_text="Content",
            metadata=metadata,
        )

        header = builder.build_header(ko)
        assert "Date: Unknown|" in header


class TestBuildForEmbedding:
    """Tests for build_for_embedding method."""

    def test_concatenates_header_and_content(
        self, builder: ContextBuilder, sample_ko: KnowledgeObject
    ) -> None:
        """Embedding text is header + newline + content."""
        text = builder.build_for_embedding(sample_ko)

        assert text.startswith("[Source:")
        assert "\n" in text
        assert "Test content for embedding." in text

    def test_preserves_content(self, builder: ContextBuilder, sample_ko: KnowledgeObject) -> None:
        """Content is preserved after header."""
        text = builder.build_for_embedding(sample_ko)
        lines = text.split("\n", 1)

        assert len(lines) == 2
        assert lines[1] == sample_ko.content_text


class TestBuildBatchForEmbedding:
    """Tests for build_batch_for_embedding method."""

    def test_batch_builds_all(self, builder: ContextBuilder, sample_ko: KnowledgeObject) -> None:
        """Batch builds embedding texts for all objects."""
        objects = [sample_ko, sample_ko, sample_ko]
        texts = builder.build_batch_for_embedding(objects)

        assert len(texts) == 3
        assert all(t.startswith("[Source:") for t in texts)

    def test_empty_batch(self, builder: ContextBuilder) -> None:
        """Empty batch returns empty list."""
        texts = builder.build_batch_for_embedding([])
        assert texts == []
