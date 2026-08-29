"""Unit tests for ObjectBuilder service."""

from datetime import datetime, timezone

import pytest

from app.core.utils import compute_text_hash
from app.models.enriched_article import EnrichedArticle
from app.models.metadata import ExtractionResult
from app.models.normalized_article import NormalizedArticle
from app.services.knowledge.object_builder import ObjectBuilder


@pytest.fixture
def builder() -> ObjectBuilder:
    """Provide an ObjectBuilder instance."""
    return ObjectBuilder()


@pytest.fixture
def sample_extraction() -> ExtractionResult:
    """Provide a valid ExtractionResult."""
    return ExtractionResult(
        summary="A concise summary about AI advancements.",
        topics=["AI", "Machine Learning"],
        entities=["OpenAI", "GPT-4"],
        relevance_score=0.95,
    )


@pytest.fixture
def sample_normalized_article() -> NormalizedArticle:
    """Provide a valid NormalizedArticle."""
    return NormalizedArticle(
        article_id="norm_id_123",
        title="The Future of AI",
        content="Artificial intelligence is transforming the world.",
        url="https://example.com/future-of-ai",
        source_name="tech_blog",
        source_type="rss",
        author="Jane Doe",
        published_date=datetime(2025, 1, 1, 12, 0, 0),
        fetched_at=datetime(2025, 1, 2, 10, 0, 0),
        raw_content_hash="raw_hash_abc",
    )


# ==============================================================================
# Successful Build Tests
# ==============================================================================


class TestSuccessfulBuild:
    """Tests for successful KnowledgeObject construction."""

    def test_build_success(
        self,
        builder: ObjectBuilder,
        sample_normalized_article: NormalizedArticle,
        sample_extraction: ExtractionResult,
    ) -> None:
        """Verify that a valid EnrichedArticle produces a correct KnowledgeObject."""
        enriched = EnrichedArticle(
            article=sample_normalized_article,
            extraction=sample_extraction,
            extraction_status="success",
        )

        kos = builder.build([enriched])

        assert len(kos) == 1
        ko = kos[0]

        # Verify provenance fields
        assert ko.source_type == "rss"
        assert ko.source_name == "tech_blog"
        assert ko.external_id == "norm_id_123"
        assert ko.source_url == "https://example.com/future-of-ai"

        # Verify content hash
        expected_hash = compute_text_hash(sample_normalized_article.content)
        assert ko.content_hash == expected_hash

        # Verify content
        assert ko.title == "The Future of AI"
        assert ko.content_text == "Artificial intelligence is transforming the world."
        assert ko.metadata == sample_extraction

        # Verify stealth integration fields (should be None initially)
        assert ko.embedding_vector is None
        assert ko.vector_db_id is None

        # Verify timestamps
        assert ko.published_at == datetime(2025, 1, 1, 12, 0, 0)
        assert ko.fetched_at == datetime(2025, 1, 2, 10, 0, 0)

        # Verify version tracking
        assert ko.parser_version == "1.0.0"
        assert ko.normalizer_version == "1.0.0"
        assert ko.extractor_version == "1.0.0"


# ==============================================================================
# Filtering Tests
# ==============================================================================


class TestFiltering:
    """Tests for filtering failed extractions."""

    def test_build_skips_failed_extraction(
        self,
        builder: ObjectBuilder,
        sample_normalized_article: NormalizedArticle,
        sample_extraction: ExtractionResult,
    ) -> None:
        """Verify that articles with failed extraction are skipped."""
        enriched_failed = EnrichedArticle(
            article=sample_normalized_article,
            extraction=None,
            extraction_status="failed",
            extraction_error="LLM Timeout",
        )
        enriched_success = EnrichedArticle(
            article=sample_normalized_article,
            extraction=sample_extraction,
            extraction_status="success",
        )

        kos = builder.build([enriched_failed, enriched_success])

        assert len(kos) == 1
        assert kos[0].metadata == sample_extraction

    def test_build_skips_none_extraction_with_success_status(
        self,
        builder: ObjectBuilder,
        sample_normalized_article: NormalizedArticle,
    ) -> None:
        """Verify that articles with None extraction are skipped even if status is success."""
        # Edge case: status is success but extraction object is missing
        enriched = EnrichedArticle(
            article=sample_normalized_article,
            extraction=None,
            extraction_status="success",
        )

        kos = builder.build([enriched])
        assert len(kos) == 0

    def test_build_skips_skipped_status(
        self,
        builder: ObjectBuilder,
        sample_normalized_article: NormalizedArticle,
        sample_extraction: ExtractionResult,
    ) -> None:
        """Verify that articles with skipped status are skipped."""
        enriched = EnrichedArticle(
            article=sample_normalized_article,
            extraction=sample_extraction,
            extraction_status="skipped",
        )

        kos = builder.build([enriched])
        assert len(kos) == 0


# ==============================================================================
# Edge Case Tests
# ==============================================================================


class TestEdgeCases:
    """Tests for edge cases and defensive programming."""

    def test_build_handles_missing_fetched_at(
        self,
        builder: ObjectBuilder,
        sample_extraction: ExtractionResult,
    ) -> None:
        """Verify that missing fetched_at falls back to current time."""
        article = NormalizedArticle(
            article_id="norm_id_missing_fetched",
            title="Test",
            content="Content",
            url="https://example.com",
            source_name="src",
            source_type="rss",
            author=None,
            published_date=None,
            fetched_at=None,  # Missing fetched_at
            raw_content_hash="hash",
        )
        enriched = EnrichedArticle(
            article=article,
            extraction=sample_extraction,
            extraction_status="success",
        )

        before = datetime.now(timezone.utc)
        kos = builder.build([enriched])
        after = datetime.now(timezone.utc)

        assert len(kos) == 1
        # Should fallback to a recent datetime
        assert before <= kos[0].fetched_at <= after

    def test_build_empty_list(self, builder: ObjectBuilder) -> None:
        """Verify that empty input produces empty output."""
        kos = builder.build([])
        assert len(kos) == 0
