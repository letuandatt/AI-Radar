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
    PersistenceResult,
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
    """Provide a mocked KnowledgeObjectAssembler returning item-level results.

    Every enriched article is reported as "created" so the honest-checkpoint
    marking behaves like a fully successful assembly.
    """
    assembler = MagicMock(spec=KnowledgeObjectAssembler)

    def _assemble(enriched_articles: list[EnrichedArticle]) -> AssemblyResult:
        items = [
            PersistenceResult(
                url=ea.article.url,
                content_hash=compute_content_hash(ea.article.url, ea.article.title),
                status="created",
            )
            for ea in enriched_articles
        ]
        return AssemblyResult(
            total_input=len(enriched_articles),
            built_count=len(items),
            valid_count=len(items),
            invalid_count=0,
            created_count=len(items),
            updated_count=0,
            skipped_count=0,
            items=items,
        )

    assembler.assemble.side_effect = _assemble
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


# ==============================================================================
# Honest Checkpoint Tests (Wiring & Fix Plan A4)
# ==============================================================================


class TestHonestCheckpoint:
    """Checkpoint "stored" must reflect real persistence, item by item."""

    @staticmethod
    def _assembly_with_statuses(
        enriched_articles: list[EnrichedArticle],
        statuses: list[str],
    ) -> AssemblyResult:
        items = [
            PersistenceResult(
                url=ea.article.url,
                content_hash=compute_content_hash(ea.article.url, ea.article.title),
                status=status,
                error="db locked" if status == "failed" else None,
            )
            for ea, status in zip(enriched_articles, statuses)
        ]
        return AssemblyResult(
            total_input=len(enriched_articles),
            built_count=sum(1 for s in statuses if s != "failed"),
            valid_count=sum(1 for s in statuses if s in ("created", "updated", "skipped")),
            invalid_count=sum(1 for s in statuses if s == "failed"),
            created_count=sum(1 for s in statuses if s == "created"),
            updated_count=sum(1 for s in statuses if s == "updated"),
            skipped_count=sum(1 for s in statuses if s == "skipped"),
            items=items,
        )

    def test_failed_persistence_is_not_marked_stored(
        self,
        mock_cleaning: MagicMock,
        mock_normalization: MagicMock,
        mock_extraction: MagicMock,
        state_service: ProcessingStateService,
        sample_article: RawArticle,
    ) -> None:
        """Assembly persists 0/1 items → that article must NOT be stored."""
        assembler = MagicMock(spec=KnowledgeObjectAssembler)
        assembler.assemble.side_effect = lambda enriched: self._assembly_with_statuses(
            enriched, ["failed"]
        )

        pipeline = ProcessingPipeline(
            cleaning_stage=mock_cleaning,
            normalization_stage=mock_normalization,
            extraction_stage=mock_extraction,
            assembler=assembler,
            state_service=state_service,
        )
        result = pipeline.run([sample_article])

        c_hash = compute_content_hash(sample_article.url, sample_article.title)
        state = state_service.get_status(c_hash)
        assert state is not None
        assert state.stage == "stored"
        assert state.status == "failed"
        assert result.objects_created == 0
        assert result.errors[0]["stage"] == "stored"
        assert result.errors[0]["error_message"] == "db locked"

    def test_all_failed_persistence_marks_nothing_stored(
        self,
        mock_cleaning: MagicMock,
        mock_normalization: MagicMock,
        mock_extraction: MagicMock,
        state_service: ProcessingStateService,
    ) -> None:
        """Assembly fails 100% → zero articles may carry a stored checkpoint."""
        articles = [
            RawArticle(
                title=f"Article {i}",
                url=f"https://example.com/{i}",
                content=f"Content {i}",
                published_date=datetime(2025, 1, 1),
                source_name="test",
            )
            for i in range(3)
        ]
        assembler = MagicMock(spec=KnowledgeObjectAssembler)
        assembler.assemble.side_effect = lambda enriched: self._assembly_with_statuses(
            enriched, ["failed"] * len(enriched)
        )

        pipeline = ProcessingPipeline(
            cleaning_stage=mock_cleaning,
            normalization_stage=mock_normalization,
            extraction_stage=mock_extraction,
            assembler=assembler,
            state_service=state_service,
        )
        result = pipeline.run(articles)

        assert result.objects_created == 0
        assert result.failed_objects == 3
        for article in articles:
            state = state_service.get_status(compute_content_hash(article.url, article.title))
            assert state is not None
            assert not (state.stage == "stored" and state.status == "success")

    def test_partial_persistence_marks_only_persisted_items(
        self,
        mock_cleaning: MagicMock,
        mock_normalization: MagicMock,
        mock_extraction: MagicMock,
        state_service: ProcessingStateService,
    ) -> None:
        """3/5 persisted → exactly those hashes stored, the rest failed."""
        articles = [
            RawArticle(
                title=f"Article {i}",
                url=f"https://example.com/{i}",
                content=f"Content {i}",
                published_date=datetime(2025, 1, 1),
                source_name="test",
            )
            for i in range(5)
        ]
        statuses = ["created", "updated", "created", "failed", "failed"]
        assembler = MagicMock(spec=KnowledgeObjectAssembler)
        assembler.assemble.side_effect = lambda enriched: self._assembly_with_statuses(
            enriched, statuses
        )

        pipeline = ProcessingPipeline(
            cleaning_stage=mock_cleaning,
            normalization_stage=mock_normalization,
            extraction_stage=mock_extraction,
            assembler=assembler,
            state_service=state_service,
        )
        result = pipeline.run(articles)

        assert result.objects_created == 2
        assert result.objects_updated == 1
        assert result.failed_objects == 2
        for article, status in zip(articles, statuses):
            state = state_service.get_status(compute_content_hash(article.url, article.title))
            assert state is not None
            assert state.stage == "stored"
            assert state.status == ("success" if status in ("created", "updated") else "failed")

    def test_skipped_persistence_is_replay_safe(
        self,
        mock_cleaning: MagicMock,
        mock_normalization: MagicMock,
        mock_extraction: MagicMock,
        state_service: ProcessingStateService,
        sample_article: RawArticle,
    ) -> None:
        """Idempotent skip (content unchanged) counts as stored on re-runs."""
        assembler = MagicMock(spec=KnowledgeObjectAssembler)
        assembler.assemble.side_effect = lambda enriched: self._assembly_with_statuses(
            enriched, ["skipped"]
        )

        pipeline = ProcessingPipeline(
            cleaning_stage=mock_cleaning,
            normalization_stage=mock_normalization,
            extraction_stage=mock_extraction,
            assembler=assembler,
            state_service=state_service,
        )
        result = pipeline.run([sample_article])
        assert result.objects_created == 0

        # Re-run: the skipped-persisted article must be checkpoint-skipped
        result_2 = pipeline.run([sample_article])
        assert result_2.skipped_objects == 1
        assert result_2.cleaned == 0


# ==============================================================================
# Async Pipeline Tests (Wiring & Fix Plan A5)
# ==============================================================================


class TestAsyncPipeline:
    """run_async: deterministic stages sync, extraction as ONE async batch."""

    def _pipeline(
        self,
        mock_cleaning: MagicMock,
        mock_normalization: MagicMock,
        state_service: ProcessingStateService,
        assembler: MagicMock,
        extraction_stage: MagicMock | None = None,
        batch_extraction_stage=None,
    ) -> ProcessingPipeline:
        return ProcessingPipeline(
            cleaning_stage=mock_cleaning,
            normalization_stage=mock_normalization,
            extraction_stage=extraction_stage,
            assembler=assembler,
            state_service=state_service,
            batch_extraction_stage=batch_extraction_stage,
        )

    @staticmethod
    def _enriched(norm: NormalizedArticle, status: str = "success") -> EnrichedArticle:
        return EnrichedArticle(
            article=norm,
            extraction=ExtractionResult(
                summary="sum", topics=["t"], entities=["e"], relevance_score=0.5
            )
            if status == "success"
            else None,
            extraction_status=status,
            extraction_error="LLM exploded" if status != "success" else None,
        )

    async def test_run_async_batch_extraction(
        self,
        mock_cleaning: MagicMock,
        mock_normalization: MagicMock,
        mock_assembler: MagicMock,
        state_service: ProcessingStateService,
        sample_article: RawArticle,
    ) -> None:
        """Happy path: one batch call, order preserved, article assembled."""
        calls: list[list[NormalizedArticle]] = []

        async def batch(articles: list[NormalizedArticle]) -> list[EnrichedArticle]:
            calls.append(articles)
            return [self._enriched(articles[0])]

        pipeline = self._pipeline(
            mock_cleaning,
            mock_normalization,
            state_service,
            mock_assembler,
            batch_extraction_stage=batch,
        )
        result = await pipeline.run_async([sample_article])

        assert len(calls) == 1  # extraction ran as ONE batch call
        assert result.extracted == 1
        assert result.objects_created == 1
        c_hash = compute_content_hash(sample_article.url, sample_article.title)
        state = state_service.get_status(c_hash)
        assert state is not None
        assert state.stage == "stored"
        assert state.status == "success"

    async def test_run_async_mixed_batch_results(
        self,
        mock_cleaning: MagicMock,
        mock_normalization: MagicMock,
        state_service: ProcessingStateService,
    ) -> None:
        """One article explodes in the batch → the other still assembles."""
        good = RawArticle(
            title="Good",
            url="https://example.com/good",
            content="Good content",
            published_date=datetime(2025, 1, 1),
            source_name="test",
        )
        bad = RawArticle(
            title="Bad",
            url="https://example.com/bad",
            content="Bad content",
            published_date=datetime(2025, 1, 1),
            source_name="test",
        )
        assembler = MagicMock(spec=KnowledgeObjectAssembler)
        assembler.assemble.side_effect = lambda enriched: AssemblyResult(
            total_input=len(enriched),
            built_count=len(enriched),
            valid_count=len(enriched),
            invalid_count=0,
            created_count=len(enriched),
            updated_count=0,
            skipped_count=0,
            items=[
                PersistenceResult(
                    url=ea.article.url,
                    content_hash=compute_content_hash(ea.article.url, ea.article.title),
                    status="created",
                )
                for ea in enriched
            ],
        )

        async def batch(articles: list[NormalizedArticle]) -> list[EnrichedArticle]:
            return [
                self._enriched(articles[0], status="success"),
                self._enriched(articles[1], status="failed"),
            ]

        pipeline = self._pipeline(
            mock_cleaning,
            mock_normalization,
            state_service,
            assembler,
            batch_extraction_stage=batch,
        )
        result = await pipeline.run_async([good, bad])

        assert result.extracted == 1
        assert result.objects_created == 1  # good article still assembled
        assert result.failed_objects == 1
        assert result.errors[0]["stage"] == "extracted"
        bad_state = state_service.get_status(compute_content_hash(bad.url, bad.title))
        assert bad_state is not None
        assert bad_state.status == "failed"

    async def test_run_async_sync_fallback(
        self,
        mock_cleaning: MagicMock,
        mock_normalization: MagicMock,
        mock_extraction: MagicMock,
        mock_assembler: MagicMock,
        state_service: ProcessingStateService,
        sample_article: RawArticle,
    ) -> None:
        """Without a batch stage, run_async falls back to the sync stage."""
        pipeline = self._pipeline(
            mock_cleaning,
            mock_normalization,
            state_service,
            mock_assembler,
            extraction_stage=mock_extraction,
        )
        result = await pipeline.run_async([sample_article])

        assert result.extracted == 1
        assert result.objects_created == 1

    async def test_run_async_skipped_extraction_not_failed(
        self,
        mock_cleaning: MagicMock,
        mock_normalization: MagicMock,
        mock_assembler: MagicMock,
        state_service: ProcessingStateService,
        sample_article: RawArticle,
    ) -> None:
        """Content-too-short skips are not pipeline failures."""

        async def batch(articles: list[NormalizedArticle]) -> list[EnrichedArticle]:
            return [self._enriched(articles[0], status="skipped")]

        pipeline = self._pipeline(
            mock_cleaning,
            mock_normalization,
            state_service,
            mock_assembler,
            batch_extraction_stage=batch,
        )
        result = await pipeline.run_async([sample_article])

        assert result.extracted == 0
        assert result.failed_objects == 0
        assert result.objects_created == 0
        c_hash = compute_content_hash(sample_article.url, sample_article.title)
        state = state_service.get_status(c_hash)
        assert state is not None
        assert state.stage == "extracted"
        assert state.status == "skipped"


# ==============================================================================
# Checkpoint Persistence Tests (A4 review regression)
# ==============================================================================


class TestCheckpointPersistence:
    """flush() must write checkpoints to disk — verified by reloading the
    state file in a FRESH service, not by asserting the in-memory service."""

    def _fresh_service(self, state_file: Path) -> ProcessingStateService:
        return ProcessingStateService(storage=ProcessingStateStorage(file_path=state_file))

    def test_run_persists_checkpoint_to_disk(
        self,
        mock_cleaning: MagicMock,
        mock_normalization: MagicMock,
        mock_extraction: MagicMock,
        mock_assembler: MagicMock,
        tmp_path: Path,
        sample_article: RawArticle,
    ) -> None:
        state_file = tmp_path / "persist.json"
        pipeline = ProcessingPipeline(
            cleaning_stage=mock_cleaning,
            normalization_stage=mock_normalization,
            extraction_stage=mock_extraction,
            assembler=mock_assembler,
            state_service=self._fresh_service(state_file),
        )
        pipeline.run([sample_article])

        reloaded = self._fresh_service(state_file)
        state = reloaded.get_status(compute_content_hash(sample_article.url, sample_article.title))
        assert state is not None
        assert state.stage == "stored"
        assert state.status == "success"

    async def test_run_async_persists_checkpoint_to_disk(
        self,
        mock_cleaning: MagicMock,
        mock_normalization: MagicMock,
        mock_assembler: MagicMock,
        tmp_path: Path,
        sample_article: RawArticle,
    ) -> None:
        state_file = tmp_path / "persist.json"

        async def batch(articles: list[NormalizedArticle]) -> list[EnrichedArticle]:
            return [
                EnrichedArticle(
                    article=a,
                    extraction=ExtractionResult(
                        summary="s", topics=["t"], entities=["e"], relevance_score=0.5
                    ),
                    extraction_status="success",
                )
                for a in articles
            ]

        pipeline = ProcessingPipeline(
            cleaning_stage=mock_cleaning,
            normalization_stage=mock_normalization,
            extraction_stage=None,
            assembler=mock_assembler,
            state_service=self._fresh_service(state_file),
            batch_extraction_stage=batch,
        )
        await pipeline.run_async([sample_article])

        reloaded = self._fresh_service(state_file)
        state = reloaded.get_status(compute_content_hash(sample_article.url, sample_article.title))
        assert state is not None
        assert state.stage == "stored"
        assert state.status == "success"
