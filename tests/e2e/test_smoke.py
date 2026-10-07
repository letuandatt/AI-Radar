"""E2E smoke tests (P1.10): the four incident scenarios that matter.

FakeSource articles + fake LLM + REAL SQLite/state storage — the same
component stack the entrypoints use. Scenario names map to the P1.10 DoD:
source -> persist, restart -> no re-acquire, 429 -> retry -> success,
LLM fail -> failed checkpoint -> replay.
"""

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.integrations.llm.groq_provider import GroqProvider
from app.integrations.llm.provider_chain import LLMProviderChain
from app.models.article import RawArticle
from app.models.enriched_article import EnrichedArticle
from app.models.metadata import ExtractionResult
from app.models.normalized_article import NormalizedArticle
from app.models.result import AcquisitionResult
from app.pipelines.knowledge_update import run_knowledge_update
from app.pipelines.processing import ProcessingPipeline
from app.services.extraction.content_sanitizer import ContentSanitizer
from app.services.extraction.metadata_extractor import MetadataExtractor
from app.services.knowledge.object_assembler import KnowledgeObjectAssembler
from app.services.knowledge.object_builder import ObjectBuilder
from app.services.knowledge.object_validator import KnowledgeObjectValidator
from app.services.processing_state_service import ProcessingStateService
from app.storage.knowledge.sqlite_store import SQLiteKnowledgeStore
from app.storage.processing_state import ProcessingStateStorage


def _normalize(raw: RawArticle) -> NormalizedArticle:
    return NormalizedArticle(
        article_id=f"norm_{abs(hash(raw.url)) & 0xFFFFFFFF}",
        title=raw.title,
        content=raw.content,
        url=raw.url,
        source_name=raw.source_name,
        source_type="rss",
        author=None,
        published_date=raw.published_date,
        fetched_at=datetime.now(timezone.utc),
        raw_content_hash="raw",
    )


def _fake_source(slug: str) -> RawArticle:
    return RawArticle(
        title=f"E2E Article {slug}",
        url=f"https://example.com/e2e/{slug}",
        content="A" * 200,
        published_date=datetime(2026, 10, 7, tzinfo=timezone.utc),
        source_name="fake_source",
    )


def _acquisition_result(articles: list[RawArticle]) -> AcquisitionResult:
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


class _Stack:
    """The batch stack: real assembler/store/state, injectable extraction."""

    def __init__(self, tmp_path: Path, batch=None) -> None:
        self.store = SQLiteKnowledgeStore(db_path=tmp_path / "knowledge.db")
        self.state_file = tmp_path / "state.json"
        self.state_service = ProcessingStateService(
            storage=ProcessingStateStorage(file_path=self.state_file)
        )
        self.assembler = KnowledgeObjectAssembler(
            builder=ObjectBuilder(),
            validator=KnowledgeObjectValidator(),
            store=self.store,
        )

        async def _async_batch(articles):
            result = batch(articles)
            if asyncio.iscoroutine(result):
                result = await result
            return result

        self.pipeline = ProcessingPipeline(
            cleaning_stage=lambda a: a,
            normalization_stage=_normalize,
            extraction_stage=None,
            assembler=self.assembler,
            state_service=self.state_service,
            batch_extraction_stage=_async_batch,
        )

    @staticmethod
    def success_batch(articles: list[NormalizedArticle]) -> list[EnrichedArticle]:
        return [
            EnrichedArticle(
                article=a,
                extraction=ExtractionResult(
                    summary=f"Summary of {a.title}",
                    topics=["ai"],
                    entities=["e"],
                    relevance_score=0.9,
                ),
                extraction_status="success",
            )
            for a in articles
        ]


class TestSourceToPersist:
    def test_fake_source_articles_reach_the_store(self, tmp_path: Path):
        """DoD scenario 1: FakeSource -> acquisition -> processing -> store."""
        stack = _Stack(tmp_path, batch=lambda articles: _Stack.success_batch(articles))
        articles = [_fake_source("a"), _fake_source("b")]

        result = run_knowledge_update(_acquisition_result(articles), stack.pipeline)

        assert result is not None
        assert result.objects_created == 2
        assert stack.store.count() == 2


class TestRestartScenario:
    def test_restart_does_not_reacquire_or_reextract(self, tmp_path: Path):
        """DoD scenario 2: restart -> checkpoints skip, zero new LLM calls."""
        state_file = tmp_path / "state.json"
        articles = [_fake_source("a"), _fake_source("b")]

        def make_stack(batch):
            store = SQLiteKnowledgeStore(db_path=tmp_path / "knowledge.db")
            state = ProcessingStateService(storage=ProcessingStateStorage(file_path=state_file))

            async def _async_batch(articles):
                return batch(articles)

            return ProcessingPipeline(
                cleaning_stage=lambda a: a,
                normalization_stage=_normalize,
                extraction_stage=None,
                assembler=KnowledgeObjectAssembler(
                    builder=ObjectBuilder(),
                    validator=KnowledgeObjectValidator(),
                    store=store,
                ),
                state_service=state,
                batch_extraction_stage=_async_batch,
            )

        calls: list[int] = []

        def first_batch(articles_batch: list[NormalizedArticle]) -> list[EnrichedArticle]:
            calls.append(len(articles_batch))
            return _Stack.success_batch(articles_batch)

        run_knowledge_update(_acquisition_result(articles), make_stack(first_batch))
        assert calls == [2]

        # "Restart": fresh pipeline over the same persisted state
        replay_calls: list[int] = []

        def replay_batch(articles_batch: list[NormalizedArticle]) -> list[EnrichedArticle]:
            replay_calls.append(len(articles_batch))
            return _Stack.success_batch(articles_batch)

        result = run_knowledge_update(_acquisition_result(articles), make_stack(replay_batch))

        assert result is not None
        assert result.skipped_objects == 2
        assert replay_calls == []  # nothing re-extracted
        assert SQLiteKnowledgeStore(db_path=tmp_path / "knowledge.db").count() == 2


class TestTransient429Scenario:
    def test_429_retried_then_article_stored_sync(self, tmp_path: Path, monkeypatch):
        """DoD scenario 3: 429 -> taxonomy -> backoff -> retry -> stored."""
        monkeypatch.setattr("app.integrations.llm.groq_provider.time.sleep", lambda s: None)

        # Groq provider whose first structured call hits a 429, second succeeds
        rate_limit_error = type("RateLimitErr", (Exception,), {})("429")
        rate_limit_error.status_code = 429

        ok_raw = MagicMock()
        ok_raw.usage_metadata = {"input_tokens": 100, "output_tokens": 50}
        mock_structured = MagicMock()
        mock_structured.invoke.side_effect = [
            rate_limit_error,
            {"raw": ok_raw, "parsed": _extraction(), "parsing_error": None},
        ]
        mock_llm = MagicMock()
        mock_llm.with_structured_output.return_value = mock_structured

        with patch(
            "app.integrations.llm.groq_provider.create_groq_chat_model",
            return_value=mock_llm,
        ):
            chain = LLMProviderChain([GroqProvider(model_name="qwen/qwen3.8-27b")])
            extractor = MetadataExtractor(
                llm_provider=chain,
                sanitizer=ContentSanitizer(),
                max_concurrent=2,
                min_content_length=0,
            )

            stack = _Stack(
                tmp_path,
                batch=lambda articles: extractor.extract_batch(articles),
            )
            result = run_knowledge_update(_acquisition_result([_fake_source("a")]), stack.pipeline)

        assert result is not None
        assert result.objects_created == 1  # succeeded despite the 429
        assert mock_llm.with_structured_output.return_value.invoke.call_count == 2
        assert stack.store.count() == 1


class TestLLMFailReplayScenario:
    def test_permanent_llm_fail_checkpointed_then_replayed(self, tmp_path: Path):
        """DoD scenario 4: LLM fails -> failed checkpoint -> replay succeeds."""
        state_file = tmp_path / "state.json"
        articles = [_fake_source("a")]

        def make_stack(batch):
            store = SQLiteKnowledgeStore(db_path=tmp_path / "knowledge.db")
            state = ProcessingStateService(storage=ProcessingStateStorage(file_path=state_file))

            async def _async_batch(articles):
                return batch(articles)

            return ProcessingPipeline(
                cleaning_stage=lambda a: a,
                normalization_stage=_normalize,
                extraction_stage=None,
                assembler=KnowledgeObjectAssembler(
                    builder=ObjectBuilder(),
                    validator=KnowledgeObjectValidator(),
                    store=store,
                ),
                state_service=state,
                batch_extraction_stage=_async_batch,
            )

        def failing_batch(articles_batch: list[NormalizedArticle]) -> list[EnrichedArticle]:
            return [
                EnrichedArticle(
                    article=a,
                    extraction=None,
                    extraction_status="failed",
                    extraction_error="Groq quota exhausted",
                )
                for a in articles_batch
            ]

        result = run_knowledge_update(_acquisition_result(articles), make_stack(failing_batch))
        assert result is not None
        assert result.objects_created == 0
        assert result.failed_objects == 1

        # Replay: same articles, working extraction
        result_2 = run_knowledge_update(
            _acquisition_result(articles), make_stack(lambda b: _Stack.success_batch(b))
        )
        assert result_2 is not None
        assert result_2.objects_created == 1
        assert result_2.failed_objects == 0


def _extraction() -> ExtractionResult:
    return ExtractionResult(summary="s", topics=["ai"], entities=["e"], relevance_score=0.9)
