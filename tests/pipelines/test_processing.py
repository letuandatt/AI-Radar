"""Unit tests for ProcessingPipeline orchestration."""

from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.core.utils import compute_content_hash
from app.models.article import RawArticle
from app.models.enriched_article import EnrichedArticle
from app.models.metadata import ExtractionResult
from app.models.normalized_article import NormalizedArticle
from app.pipelines.processing import ProcessingPipeline
from app.services.knowledge.object_assembler import (
    AssemblyResult,
    KnowledgeObjectAssembler,
)
from app.services.processing_state_service import ProcessingStateService
from app.storage.processing_state import ProcessingStateStorage


@pytest.fixture
def state_service(tmp_path: Path) -> ProcessingStateService:
    """Provide a ProcessingStateService backed by temp file storage."""
    storage = ProcessingStateStorage(file_path=tmp_path / "state.json")
    return ProcessingStateService(storage=storage)


@pytest.fixture
def mock_assembler() -> MagicMock:
    """Provide a mocked KnowledgeObjectAssembler."""
    assembler = MagicMock(spec=KnowledgeObjectAssembler)
    assembler.assemble.return_value = AssemblyResult(
        total_input=1,
        built_count=1,
        valid_count=1,
        invalid_count=0,
        created_count=1,
        updated_count=0,
    )
    return assembler


@pytest.fixture
def mock_cleaning() -> MagicMock:
    """Provide a mocked cleaning stage that passes through the article."""
    return MagicMock(side_effect=lambda x: x)


@pytest.fixture
def mock_normalization() -> MagicMock:
    """Provide a mocked normalization stage."""

    def _norm(raw: RawArticle) -> NormalizedArticle:
        return NormalizedArticle(
            article_id="norm_id",
            title=raw.title,
            content=raw.content,
            url=raw.url,
            source_name=raw.source_name,
            source_type="rss",
            author=None,
            published_date=raw.published_date,
            fetched_at=datetime(2025, 1, 1),
            raw_content_hash="raw_hash",
        )

    return MagicMock(side_effect=_norm)


@pytest.fixture
def mock_extraction() -> MagicMock:
    """Provide a mocked extraction stage."""

    def _extract(norm: NormalizedArticle) -> EnrichedArticle:
        return EnrichedArticle(
            article=norm,
            extraction=ExtractionResult(
                summary="sum",
                topics=["t"],
                entities=["e"],
                relevance_score=0.5,
            ),
            extraction_status="success",
        )

    return MagicMock(side_effect=_extract)


@pytest.fixture
def sample_article() -> RawArticle:
    """Provide a sample RawArticle for testing."""
    return RawArticle(
        title="Test Article",
        url="https://example.com/test",
        content="Test content",
        published_date=datetime(2025, 1, 1),
        source_name="test_source",
    )


@pytest.fixture
def pipeline(
    mock_cleaning: MagicMock,
    mock_normalization: MagicMock,
    mock_extraction: MagicMock,
    mock_assembler: MagicMock,
    state_service: ProcessingStateService,
) -> ProcessingPipeline:
    """Provide a fully wired ProcessingPipeline with mocked stages."""
    return ProcessingPipeline(
        cleaning_stage=mock_cleaning,
        normalization_stage=mock_normalization,
        extraction_stage=mock_extraction,
        assembler=mock_assembler,
        state_service=state_service,
    )


# ==============================================================================
# Successful Pipeline Tests
# ==============================================================================


class TestSuccessfulPipeline:
    """Tests for the happy path where all stages succeed."""

    def test_run_success_all_stages(
        self, pipeline: ProcessingPipeline, sample_article: RawArticle
    ) -> None:
        result = pipeline.run([sample_article])

        assert result.total_input == 1
        assert result.cleaned == 1
        assert result.normalized == 1
        assert result.extracted == 1
        assert result.objects_created == 1
        assert result.objects_updated == 0
        assert result.failed_objects == 0
        assert result.skipped_objects == 0
        assert result.processing_duration >= 0
        assert result.errors == []

    def test_run_empty_input(self, pipeline: ProcessingPipeline) -> None:
        result = pipeline.run([])

        assert result.total_input == 0
        assert result.cleaned == 0
        assert result.failed_objects == 0
        assert result.processing_duration >= 0


# ==============================================================================
# Checkpoint / Skip Tests
# ==============================================================================


class TestCheckpoint:
    """Tests for checkpoint behavior (skipping already-stored items)."""

    def test_skips_already_stored(
        self,
        pipeline: ProcessingPipeline,
        state_service: ProcessingStateService,
        sample_article: RawArticle,
    ) -> None:
        """Articles with state 'stored' + 'success' are skipped."""
        c_hash = compute_content_hash(sample_article.url, sample_article.title)
        state_service.update_status(c_hash, "stored", "success")

        result = pipeline.run([sample_article])

        assert result.skipped_objects == 1
        assert result.cleaned == 0
        assert result.objects_created == 0

    def test_retries_failed_items(
        self,
        pipeline: ProcessingPipeline,
        state_service: ProcessingStateService,
        sample_article: RawArticle,
    ) -> None:
        """Articles with state 'failed' are re-processed (not skipped)."""
        c_hash = compute_content_hash(sample_article.url, sample_article.title)
        state_service.update_status(c_hash, "cleaned", "failed", error_message="Old error")

        result = pipeline.run([sample_article])

        assert result.skipped_objects == 0
        assert result.cleaned == 1
        assert result.objects_created == 1


# ==============================================================================
# Failure Handling Tests
# ==============================================================================


class TestFailureHandling:
    """Tests for fault-tolerant behavior when stages raise exceptions."""

    def test_handles_cleaning_failure(
        self,
        pipeline: ProcessingPipeline,
        sample_article: RawArticle,
        mock_cleaning: MagicMock,
    ) -> None:
        mock_cleaning.side_effect = ValueError("Cleaning error")

        result = pipeline.run([sample_article])

        assert result.failed_objects == 1
        assert result.cleaned == 0
        assert len(result.errors) == 1
        assert result.errors[0]["stage"] == "cleaned"
        assert "Cleaning error" in result.errors[0]["error_message"]

    def test_handles_normalization_failure(
        self,
        pipeline: ProcessingPipeline,
        sample_article: RawArticle,
        mock_normalization: MagicMock,
    ) -> None:
        mock_normalization.side_effect = RuntimeError("Norm error")

        result = pipeline.run([sample_article])

        assert result.failed_objects == 1
        assert result.cleaned == 1
        assert result.normalized == 0
        assert result.errors[0]["stage"] == "normalized"

    def test_handles_extraction_failure(
        self,
        pipeline: ProcessingPipeline,
        sample_article: RawArticle,
        mock_extraction: MagicMock,
    ) -> None:
        mock_extraction.side_effect = TimeoutError("LLM timeout")

        result = pipeline.run([sample_article])

        assert result.failed_objects == 1
        assert result.cleaned == 1
        assert result.normalized == 1
        assert result.extracted == 0
        assert result.errors[0]["stage"] == "extracted"
        assert result.errors[0]["error_type"] == "TimeoutError"

    def test_failure_does_not_crash_pipeline(
        self,
        pipeline: ProcessingPipeline,
        mock_cleaning: MagicMock,
    ) -> None:
        """A failure on one article must not stop processing of others."""
        good_article = RawArticle(
            title="Good",
            url="https://example.com/good",
            content="Good content",
            published_date=datetime(2025, 1, 1),
            source_name="test",
        )
        bad_article = RawArticle(
            title="Bad",
            url="https://example.com/bad",
            content="Bad content",
            published_date=datetime(2025, 1, 1),
            source_name="test",
        )

        def cleaning_side_effect(article: RawArticle) -> RawArticle:
            if article.title == "Bad":
                raise ValueError("Bad article")
            return article

        mock_cleaning.side_effect = cleaning_side_effect

        result = pipeline.run([bad_article, good_article])

        assert result.total_input == 2
        assert result.failed_objects == 1
        assert result.cleaned == 1
        assert result.objects_created == 1


# ==============================================================================
# Replay Tests
# ==============================================================================


class TestReplay:
    """Tests for the replay_failed mechanism."""

    def test_replay_failed_filters_correctly(
        self,
        pipeline: ProcessingPipeline,
        state_service: ProcessingStateService,
        sample_article: RawArticle,
    ) -> None:
        article_2 = RawArticle(
            title="Test 2",
            url="https://example.com/test2",
            content="Content 2",
            published_date=datetime(2025, 1, 1),
            source_name="test_source",
        )

        # First run: both succeed
        pipeline.run([sample_article, article_2])

        # Manually mark article_2 as failed
        c_hash_2 = compute_content_hash(article_2.url, article_2.title)
        state_service.update_status(c_hash_2, "cleaned", "failed")

        # Replay should only process article_2
        result = pipeline.replay_failed([sample_article, article_2])

        assert result.total_input == 1
        assert result.cleaned == 1

    def test_replay_no_failed_items(
        self, pipeline: ProcessingPipeline, sample_article: RawArticle
    ) -> None:
        pipeline.run([sample_article])  # Succeeds

        result = pipeline.replay_failed([sample_article])

        assert result.total_input == 0
        assert result.processing_duration == 0.0
