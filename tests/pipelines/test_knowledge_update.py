"""Integration tests: acquisition articles reach the Knowledge Repository.

Wiring & Fix Plan A1/A4/A5 — the critical end-to-end check:
FakeSource articles → ProcessingPipeline (real assembler + SQLite store)
→ ≥1 KnowledgeObject persisted, checkpoint honest, replay skips stored items.
"""

from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.core.utils import compute_content_hash
from app.models.article import RawArticle
from app.models.enriched_article import EnrichedArticle
from app.models.metadata import ExtractionResult
from app.models.normalized_article import NormalizedArticle
from app.models.result import AcquisitionResult
from app.pipelines.knowledge_update import run_knowledge_update
from app.pipelines.processing import ProcessingPipeline
from app.services.knowledge.object_assembler import KnowledgeObjectAssembler
from app.services.knowledge.object_builder import ObjectBuilder
from app.services.knowledge.object_validator import KnowledgeObjectValidator
from app.services.processing_state_service import ProcessingStateService
from app.storage.knowledge.sqlite_store import SQLiteKnowledgeStore
from app.storage.processing_state import ProcessingStateStorage


def _normalize(raw) -> NormalizedArticle:
    return NormalizedArticle(
        article_id=f"norm_{hash(raw.url) & 0xFFFFFFFF}",
        title=raw.title,
        content=raw.content,
        url=raw.url,
        source_name=raw.source_name,
        source_type="rss",
        author=None,
        published_date=raw.published_date,
        fetched_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        raw_content_hash="raw_hash",
    )


@pytest.fixture
def processing_pipeline(tmp_path: Path) -> ProcessingPipeline:
    """Pipeline with REAL assembler + SQLite store; only the LLM is faked."""
    store = SQLiteKnowledgeStore(db_path=tmp_path / "knowledge.db")
    state_service = ProcessingStateService(
        storage=ProcessingStateStorage(file_path=tmp_path / "state.json")
    )
    assembler = KnowledgeObjectAssembler(
        builder=ObjectBuilder(),
        validator=KnowledgeObjectValidator(),
        store=store,
    )

    async def batch_extraction(articles: list[NormalizedArticle]):
        """Fake extractor: succeeds for every candidate (no real LLM)."""
        return [
            EnrichedArticle(
                article=article,
                extraction=ExtractionResult(
                    summary="s",
                    topics=["t"],
                    entities=["e"],
                    relevance_score=0.5,
                ),
                extraction_status="success",
            )
            for article in articles
        ]

    return ProcessingPipeline(
        cleaning_stage=lambda article: article,
        normalization_stage=_normalize,
        extraction_stage=None,
        assembler=assembler,
        state_service=state_service,
        batch_extraction_stage=batch_extraction,
    )


def _acquisition_result(articles) -> AcquisitionResult:
    return AcquisitionResult(
        timestamp=datetime.now(),
        total_sources=1,
        successful_sources=1,
        failed_sources=0,
        total_articles=len(articles),
        execution_time=0.1,
        errors=[],
        articles=list(articles),
    )


def test_acquisition_articles_are_persisted_and_checkpointed(
    processing_pipeline: ProcessingPipeline, tmp_path: Path
) -> None:
    """A1 invariant: acquired articles become KnowledgeObjects in the store."""
    article = _sample_article("stored")
    result = run_knowledge_update(_acquisition_result([article]), processing_pipeline)

    assert result is not None
    assert result.objects_created == 1
    assert result.failed_objects == 0

    # Honest checkpoint: article is marked stored only because it persisted
    state_service = processing_pipeline._state
    state = state_service.get_status(compute_content_hash(article.url, article.title))
    assert state is not None
    assert state.stage == "stored"
    assert state.status == "success"

    # SQLite really contains the object
    assert SQLiteKnowledgeStore(db_path=tmp_path / "knowledge.db").count() == 1


def test_replay_skips_already_persisted_articles(
    processing_pipeline: ProcessingPipeline,
) -> None:
    """A second run over the same articles must checkpoint-skip, not redo."""
    article = _sample_article("replay")
    run_knowledge_update(_acquisition_result([article]), processing_pipeline)
    result_2 = run_knowledge_update(_acquisition_result([article]), processing_pipeline)

    assert result_2 is not None
    assert result_2.skipped_objects == 1
    assert result_2.cleaned == 0
    assert result_2.objects_created == 0


def test_persistence_failure_is_not_marked_stored(
    tmp_path: Path,
) -> None:
    """A4 invariant under failure: store refuses → checkpoint stays failed."""

    class _FailingStore(SQLiteKnowledgeStore):
        def save_objects(self, objects):
            raise RuntimeError("db locked")

    store = _FailingStore(db_path=tmp_path / "knowledge.db")
    state_service = ProcessingStateService(
        storage=ProcessingStateStorage(file_path=tmp_path / "state.json")
    )
    assembler = KnowledgeObjectAssembler(
        builder=ObjectBuilder(),
        validator=KnowledgeObjectValidator(),
        store=store,
    )

    async def batch_extraction(articles: list[NormalizedArticle]):
        return [
            EnrichedArticle(
                article=article,
                extraction=ExtractionResult(
                    summary="s", topics=["t"], entities=["e"], relevance_score=0.5
                ),
                extraction_status="success",
            )
            for article in articles
        ]

    pipeline = ProcessingPipeline(
        cleaning_stage=lambda article: article,
        normalization_stage=_normalize,
        extraction_stage=None,
        assembler=assembler,
        state_service=state_service,
        batch_extraction_stage=batch_extraction,
    )

    article = _sample_article("failing")
    result = run_knowledge_update(_acquisition_result([article]), pipeline)

    assert result is not None
    assert result.objects_created == 0
    assert result.failed_objects == 1
    state = state_service.get_status(compute_content_hash(article.url, article.title))
    assert state is not None
    assert state.status == "failed"


def _sample_article(slug: str) -> RawArticle:
    return RawArticle(
        title=f"Sample Article {slug}",
        url=f"https://example.com/{slug}",
        content="A" * 200,
        published_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
        source_name="test_source",
    )
