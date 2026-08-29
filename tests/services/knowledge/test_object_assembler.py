"""Unit tests for KnowledgeObjectAssembler orchestration pipeline."""

from datetime import datetime
from pathlib import Path

import pytest

from app.models.enriched_article import EnrichedArticle
from app.models.metadata import ExtractionResult
from app.models.normalized_article import NormalizedArticle
from app.services.knowledge.object_assembler import (
    AssemblyResult,
    KnowledgeObjectAssembler,
)
from app.services.knowledge.object_builder import ObjectBuilder
from app.services.knowledge.object_validator import KnowledgeObjectValidator
from app.storage.file_knowledge_store import FileKnowledgeStore


@pytest.fixture
def builder() -> ObjectBuilder:
    return ObjectBuilder()


@pytest.fixture
def validator() -> KnowledgeObjectValidator:
    return KnowledgeObjectValidator()


@pytest.fixture
def store(tmp_path: Path) -> FileKnowledgeStore:
    return FileKnowledgeStore(file_path=tmp_path / "test_store.json")


@pytest.fixture
def assembler(
    builder: ObjectBuilder,
    validator: KnowledgeObjectValidator,
    store: FileKnowledgeStore,
) -> KnowledgeObjectAssembler:
    return KnowledgeObjectAssembler(builder=builder, validator=validator, store=store)


@pytest.fixture
def sample_extraction() -> ExtractionResult:
    return ExtractionResult(
        summary="AI summary.",
        topics=["AI", "Deep Learning"],
        entities=["OpenAI", "GPT-4"],
        relevance_score=0.95,
    )


def _make_enriched_article(
    article_id: str = "norm_001",
    title: str = "Test Article",
    content: str = "Test content for the article.",
    status: str = "success",
    extraction: ExtractionResult | None = None,
) -> EnrichedArticle:
    """Helper to create an EnrichedArticle."""
    article = NormalizedArticle(
        article_id=article_id,
        title=title,
        content=content,
        url=f"https://example.com/{article_id}",
        source_name="test_source",
        source_type="rss",
        author="Tester",
        published_date=datetime(2025, 1, 1),
        fetched_at=datetime(2025, 1, 2),
        raw_content_hash="raw_hash",
    )
    return EnrichedArticle(
        article=article,
        extraction=extraction,
        extraction_status=status,
    )


# ==============================================================================
# End-to-End Pipeline Tests
# ==============================================================================


class TestAssemblyPipeline:
    """Tests for the full assemble() pipeline."""

    def test_successful_assembly(
        self,
        assembler: KnowledgeObjectAssembler,
        sample_extraction: ExtractionResult,
    ) -> None:
        """Valid enriched articles produce a successful assembly result."""
        articles = [
            _make_enriched_article(article_id="a1", extraction=sample_extraction),
            _make_enriched_article(
                article_id="a2",
                content="Different content here.",
                extraction=sample_extraction,
            ),
        ]

        result = assembler.assemble(articles)

        assert result.total_input == 2
        assert result.built_count == 2
        assert result.valid_count == 2
        assert result.invalid_count == 0
        assert result.created_count == 2
        assert result.updated_count == 0

    def test_assembly_filters_failed_extractions(
        self,
        assembler: KnowledgeObjectAssembler,
        sample_extraction: ExtractionResult,
    ) -> None:
        """Articles with failed extraction are skipped at build stage."""
        articles = [
            _make_enriched_article(article_id="good", extraction=sample_extraction),
            _make_enriched_article(article_id="bad", status="failed", extraction=None),
        ]

        result = assembler.assemble(articles)

        assert result.total_input == 2
        assert result.built_count == 1  # Only the good one built
        assert result.valid_count == 1
        assert result.created_count == 1

    def test_assembly_empty_input(self, assembler: KnowledgeObjectAssembler) -> None:
        """Empty input produces zero counts."""
        result = assembler.assemble([])

        assert result.total_input == 0
        assert result.built_count == 0
        assert result.valid_count == 0
        assert result.created_count == 0


# ==============================================================================
# Idempotent Assembly Tests
# ==============================================================================


class TestIdempotentAssembly:
    """Tests that repeated assembly does not create duplicates."""

    def test_repeated_assembly_no_duplicates(
        self,
        assembler: KnowledgeObjectAssembler,
        sample_extraction: ExtractionResult,
    ) -> None:
        """Running assemble twice with same data creates 0 new objects."""
        articles = [
            _make_enriched_article(article_id="a1", extraction=sample_extraction),
            _make_enriched_article(
                article_id="a2",
                content="Different content.",
                extraction=sample_extraction,
            ),
        ]

        # First run: creates all
        result1 = assembler.assemble(articles)
        assert result1.created_count == 2

        # Second run: all updates, no new creates
        result2 = assembler.assemble(articles)
        assert result2.created_count == 0
        assert result2.updated_count == 2

    def test_incremental_assembly(
        self,
        assembler: KnowledgeObjectAssembler,
        sample_extraction: ExtractionResult,
    ) -> None:
        """Adding new articles to existing data creates only new ones."""
        batch_1 = [
            _make_enriched_article(article_id="a1", extraction=sample_extraction),
        ]
        batch_2 = [
            _make_enriched_article(article_id="a1", extraction=sample_extraction),
            _make_enriched_article(
                article_id="a2",
                content="Brand new content.",
                extraction=sample_extraction,
            ),
        ]

        assembler.assemble(batch_1)
        result = assembler.assemble(batch_2)

        assert result.created_count == 1  # Only a2 is new
        assert result.updated_count == 1  # a1 is updated


# ==============================================================================
# AssemblyResult Tests
# ==============================================================================


class TestAssemblyResult:
    """Tests for the AssemblyResult dataclass."""

    def test_result_is_frozen(self) -> None:
        """AssemblyResult should be immutable."""
        result = AssemblyResult(
            total_input=10,
            built_count=8,
            valid_count=7,
            invalid_count=1,
            created_count=5,
            updated_count=2,
        )
        with pytest.raises(AttributeError):
            result.total_input = 99  # type: ignore[misc]
