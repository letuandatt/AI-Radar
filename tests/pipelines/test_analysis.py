"""Analysis orchestration: real persistence, retries, failures and async boundaries."""

import asyncio
import sqlite3
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.pipelines.analysis import run_analysis
from app.services.analysis.models import ContentAnalysisOutput
from app.services.repository.bootstrap import create_analysis_service
from app.storage.knowledge.sqlite_store import SQLiteKnowledgeStore
from tests.fakes.analysis import make_analysis, make_knowledge
from tests.fakes.patterns import describe


def content_output():
    return ContentAnalysisOutput(
        themes=["RAG"],
        entities={},
        sentiment="neutral",
        key_claims=["A grounded claim"],
        technical_depth="intermediate",
        confidence=0.8,
    )


@pytest.fixture
def wired(tmp_path, monkeypatch):
    from app.services.repository import bootstrap

    path = tmp_path / "knowledge.db"
    store = SQLiteKnowledgeStore(path)
    store.save_objects([make_knowledge(make_analysis(i, str(i))) for i in range(2)])
    monkeypatch.setattr(bootstrap, "get_settings", lambda: SimpleNamespace(llm_max_concurrent=2))
    provider = MagicMock()
    provider.structured_chat.side_effect = lambda prompt, schema: (
        content_output() if schema is ContentAnalysisOutput else describe(prompt, schema)
    )
    service = create_analysis_service(SimpleNamespace(sqlite_store=store), provider)
    yield service, provider, path
    store.close()


@pytest.mark.asyncio
async def test_real_sqlite_round_trip_and_same_day_rerun(wired):
    service, provider, path = wired
    first = await run_analysis(service, limit=2)
    assert len(first.content) == 2
    assert len(first.groups) == 1
    assert first.groups[0].source_count == 2
    assert len(first.patterns) == 1
    assert first.patterns[0].pattern_type == "emerging"
    assert provider.structured_chat.call_count == 3
    second = await run_analysis(service, limit=2)
    assert second.content == []
    assert second.groups == first.groups
    assert second.patterns[0].pattern_id == first.patterns[0].pattern_id
    assert second.patterns[0].first_detected == first.patterns[0].first_detected
    assert provider.structured_chat.call_count == 4  # Description reruns still call the LLM.
    with sqlite3.connect(path) as conn:
        for table, expected in [
            ("content_analyses", 2),
            ("cross_source_groups", 1),
            ("discovered_patterns", 1),
            ("pattern_snapshots", 1),
        ]:
            assert conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == expected


@pytest.mark.asyncio
async def test_partial_content_failure_stops_aggregation_and_keeps_successes(wired):
    service, provider, path = wired
    provider.structured_chat.side_effect = [RuntimeError("provider unavailable"), content_output()]
    metrics = {}
    with pytest.raises(RuntimeError, match="1/2 failed"):
        await run_analysis(service, limit=2, metrics=metrics)
    assert metrics["analysis_stage"] == "content"
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT count(*) FROM content_analyses").fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM cross_source_groups").fetchone()[0] == 0
    provider.structured_chat.side_effect = lambda prompt, schema: (
        content_output() if schema is ContentAnalysisOutput else describe(prompt, schema)
    )
    retry = await run_analysis(service, limit=2)
    assert len(retry.content) == 1
    assert len(retry.groups) == 1


@pytest.mark.asyncio
async def test_pattern_failure_leaves_completed_stages_and_honest_metrics(wired):
    service, provider, path = wired

    def respond(prompt, schema):
        if schema is ContentAnalysisOutput:
            return content_output()
        raise RuntimeError("description failed")

    provider.structured_chat.side_effect = respond
    metrics = {}
    with pytest.raises(RuntimeError, match="description failed"):
        await run_analysis(service, metrics=metrics)
    assert metrics["analysis_stage"] == "patterns"
    assert metrics["cross_source_groups_returned"] == 1
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT count(*) FROM content_analyses").fetchone()[0] == 2
        assert conn.execute("SELECT count(*) FROM cross_source_groups").fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM pattern_snapshots").fetchone()[0] == 0


@pytest.mark.asyncio
async def test_sync_stages_run_off_loop_in_order_and_skip_content():
    loop_thread = threading.get_ident()
    calls = []

    def record(stage):
        assert threading.get_ident() != loop_thread
        calls.append(stage)
        return []

    service = MagicMock()
    service.analyze_batch = AsyncMock()
    service.find_groups.side_effect = lambda days: record("groups")
    service.discover_patterns.side_effect = lambda days: record("patterns")
    result = await asyncio.wait_for(run_analysis(service, skip_content=True), timeout=2)
    assert calls == ["groups", "patterns"]
    assert result.content == result.groups == result.patterns == []
    service.analyze_batch.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("kwargs", [{"limit": 0}, {"group_days": True}, {"pattern_days": 6}])
async def test_invalid_windows_fail_before_side_effects(kwargs):
    service = MagicMock()
    with pytest.raises(ValueError):
        await run_analysis(service, **kwargs)
    assert service.mock_calls == []


def test_cached_raw_articles_reach_patterns_with_real_processing(tmp_path, monkeypatch):
    from datetime import datetime, timezone

    from app.models.article import RawArticle
    from app.models.metadata import ExtractionResult
    from app.models.result import AcquisitionResult
    from app.pipelines.knowledge_update import build_processing_pipeline, run_knowledge_update
    from app.services.repository import bootstrap

    settings = SimpleNamespace(
        llm_max_concurrent=2,
        llm_batch_size=2,
        gate_enabled=False,
        processing_state_path=tmp_path / "state.json",
    )
    monkeypatch.setattr(bootstrap, "get_settings", lambda: settings)
    store = SQLiteKnowledgeStore(tmp_path / "full.db")
    provider = MagicMock()

    def respond(prompt, schema):
        if schema is ExtractionResult:
            return ExtractionResult(
                summary="AI research", topics=["RAG"], entities=["OpenAI"], relevance_score=0.9
            )
        return content_output() if schema is ContentAnalysisOutput else describe(prompt, schema)

    provider.structured_chat.side_effect = respond
    initializer = SimpleNamespace(sqlite_store=store)
    articles = [
        RawArticle(
            title=f"AI Research Publication {i}",
            url=f"https://example.com/{i}",
            content=f"Research project {i}. " + "AI retrieval research. " * 30,
            published_date=datetime.now(timezone.utc),
            source_name=f"source-{i}",
        )
        for i in range(2)
    ]
    acquired = AcquisitionResult(
        timestamp=datetime.now(timezone.utc),
        total_sources=2,
        successful_sources=2,
        failed_sources=0,
        total_articles=2,
        execution_time=0,
        articles=articles,
    )
    try:
        processing = build_processing_pipeline(initializer, settings, provider)
        result = run_knowledge_update(acquired, processing)
        assert result.objects_created == 2 and result.failed_objects == 0
        service = create_analysis_service(initializer, provider)
        analyzed = asyncio.run(run_analysis(service, limit=2))
        assert len(analyzed.content) == 2
        assert len(analyzed.groups) == len(analyzed.patterns) == 1
        assert provider.structured_chat.call_count == 5
        replay = run_knowledge_update(acquired, processing)
        assert replay.skipped_objects == 2
    finally:
        store.close()
