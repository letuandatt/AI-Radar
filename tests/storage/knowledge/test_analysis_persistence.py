"""T169: real SQLite persistence and migration, with LLM calls mocked."""

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from app.models.knowledge_object import KnowledgeObject
from app.models.metadata import ExtractionResult
from app.prompts.loader import PromptLoader
from app.services.analysis.content_analyzer import ContentAnalyzer
from app.services.analysis.models import ContentAnalysisOutput, ContentAnalysisResult
from app.services.repository.access_service import RepositoryAccessService
from app.storage.knowledge.schema import ALL_DDL_STATEMENTS
from app.storage.knowledge.sqlite_store import SQLiteKnowledgeStore

NOW = datetime(2026, 10, 8, tzinfo=timezone.utc)


def make_item(item_id="ko-1"):
    return KnowledgeObject(
        id=item_id,
        source_type="rss",
        source_name="test",
        external_id=item_id,
        source_url=f"https://example.com/{item_id}",
        content_hash=item_id,
        fetched_at=NOW,
        title=f"Article {item_id}",
        content_text="AI research evidence.",
        metadata=ExtractionResult(
            summary="Summary", topics=["AI"], entities=[], relevance_score=0.8
        ),
    )


def make_analysis(item_id="ko-1", at=NOW, confidence=0.8):
    return ContentAnalysisResult(
        knowledge_id=item_id,
        analyzed_at=at,
        themes=["AI"],
        entities={},
        sentiment="neutral",
        key_claims=["Claim"],
        technical_depth="beginner",
        confidence=confidence,
    )


@pytest.fixture
def repository(tmp_path):
    path = tmp_path / "knowledge.db"
    store = SQLiteKnowledgeStore(path)
    store.save_objects([make_item()])
    yield store, RepositoryAccessService(store), path
    store.close()


def test_repeated_save_keeps_one_row_and_stable_identity(repository):
    store, access, path = repository
    first = make_analysis()
    access.save_content_analysis(first)

    with sqlite3.connect(path) as conn:
        original = conn.execute("SELECT analysis_id, created_at FROM content_analyses").fetchone()

    access.save_content_analysis(first)
    access.save_content_analysis(make_analysis(at=NOW + timedelta(hours=1), confidence=0.9))
    access.save_content_analysis(make_analysis(at=NOW - timedelta(hours=1), confidence=0.1))

    with sqlite3.connect(path) as conn:
        rows = conn.execute(
            "SELECT analysis_id, created_at, confidence FROM content_analyses"
        ).fetchall()

    assert rows == [(*original, 0.9)]
    assert store.query_unanalyzed() == []


@pytest.mark.asyncio
async def test_analyze_again_updates_one_row_and_batch_skips_analyzed_item(repository):
    _, access, path = repository
    llm = MagicMock()
    llm.structured_chat.return_value = ContentAnalysisOutput(
        themes=["AI"],
        entities={},
        sentiment="neutral",
        key_claims=["Claim"],
        technical_depth="beginner",
        confidence=0.8,
    )
    analyzer = ContentAnalyzer(access, llm, PromptLoader())

    await analyzer.analyze("ko-1")
    await analyzer.analyze("ko-1")

    assert await analyzer.analyze_batch(limit=10) == []
    assert llm.structured_chat.call_count == 2

    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM content_analyses").fetchone()[0] == 1


def test_concurrent_saves_across_store_instances_keep_one_latest_row(repository):
    _, access, path = repository
    other_store = SQLiteKnowledgeStore(path)
    other_access = RepositoryAccessService(other_store)

    try:

        def save(index):
            service = access if index % 2 else other_access
            service.save_content_analysis(
                make_analysis(
                    at=NOW + timedelta(seconds=index),
                    confidence=index / 20,
                )
            )

        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(save, range(10)))

        with sqlite3.connect(path) as conn:
            assert conn.execute("SELECT confidence FROM content_analyses").fetchall() == [(0.45,)]
    finally:
        other_store.close()


def seed_legacy_database(path):
    """Build the pre-T169 schema with duplicate analysis rows."""
    store = SQLiteKnowledgeStore(path)
    store.save_objects([make_item(), make_item("ko-2")])
    store.close()

    with sqlite3.connect(path) as conn:
        conn.execute("DROP INDEX uq_content_analyses_knowledge_id")

        # Actual UTC ordering differs from string ordering; the latest is inserted first.
        for row_id, item_id, timestamp, confidence in [
            ("new", "ko-1", "2026-10-08T00:00:00+00:00", 0.9),
            ("old", "ko-1", "2026-10-08T06:00:00+07:00", 0.1),
            ("other", "ko-2", "2026-10-08T00:00:00+00:00", 0.8),
        ]:
            conn.execute(
                "INSERT INTO content_analyses VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    row_id,
                    item_id,
                    timestamp,
                    '["AI"]',
                    "{}",
                    "neutral",
                    '["Claim"]',
                    "beginner",
                    confidence,
                    timestamp,
                ),
            )


def test_legacy_migration_keeps_latest_per_item_and_survives_reopen(tmp_path):
    path = tmp_path / "legacy.db"
    seed_legacy_database(path)

    for _ in range(2):
        store = SQLiteKnowledgeStore(path)
        store.close()

        with sqlite3.connect(path) as conn:
            assert conn.execute(
                "SELECT analysis_id FROM content_analyses ORDER BY analysis_id"
            ).fetchall() == [("new",), ("other",)]

            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO content_analyses SELECT 'duplicate', knowledge_id, analyzed_at, "
                    "themes_json, entities_json, sentiment, key_claims_json, technical_depth, "
                    "confidence, created_at FROM content_analyses WHERE analysis_id = 'new'"
                )


def test_failed_migration_rolls_back_duplicate_cleanup(tmp_path, monkeypatch):
    path = tmp_path / "legacy.db"
    seed_legacy_database(path)
    monkeypatch.setattr(
        "app.storage.knowledge.sqlite_store.IDX_CONTENT_ANALYSES_IDENTITY_DDL",
        "INVALID SQL",
    )

    with pytest.raises(sqlite3.OperationalError):
        SQLiteKnowledgeStore(path)

    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM content_analyses").fetchone()[0] == 3


def test_empty_legacy_schema_can_be_upgraded(tmp_path):
    path = tmp_path / "empty.db"

    with sqlite3.connect(path) as conn:
        for ddl in ALL_DDL_STATEMENTS:
            conn.execute(ddl)

    store = SQLiteKnowledgeStore(path)
    try:
        store.save_objects([make_item()])
        access = RepositoryAccessService(store)

        access.save_content_analysis(make_analysis())
        access.save_content_analysis(make_analysis())

        with sqlite3.connect(path) as conn:
            assert conn.execute("SELECT COUNT(*) FROM content_analyses").fetchone()[0] == 1
    finally:
        store.close()
