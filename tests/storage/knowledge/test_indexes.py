"""Unit tests for SQLite metadata indexing and metadata queries."""

import time
from collections.abc import Generator
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from app.core.utils import compute_text_hash
from app.models.knowledge_object import KnowledgeObject
from app.models.metadata import ExtractionResult
from app.storage.knowledge.sqlite_store import SQLiteKnowledgeStore

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "test_indexes.db"


@pytest.fixture
def store(db_path: Path) -> Generator[SQLiteKnowledgeStore, Any, None]:
    s = SQLiteKnowledgeStore(db_path=db_path)
    yield s
    s.close()


def _make_ko(
    external_id: str = "ext_001",
    source_type: str = "rss",
    source_name: str = "test_source",
    content: str = "Test content.",
    title: str = "Test Title",
    published_at: datetime | None = None,
    created_at: datetime | None = None,
) -> KnowledgeObject:
    """Helper to create a KnowledgeObject with sensible defaults."""
    metadata = ExtractionResult(
        summary="Summary",
        topics=["AI"],
        entities=["Entity"],
        relevance_score=0.9,
    )

    kwargs: dict = {
        "source_type": source_type,
        "source_name": source_name,
        "external_id": external_id,
        "source_url": f"https://example.com/{external_id}",
        "content_hash": compute_text_hash(content),
        "fetched_at": datetime(2025, 1, 2, 10, 0, 0, tzinfo=timezone.utc),
        "title": title,
        "content_text": content,
        "metadata": metadata,
    }

    if published_at is not None:
        kwargs["published_at"] = published_at

    if created_at is not None:
        kwargs["created_at"] = created_at

    return KnowledgeObject(**kwargs)


def _get_index_names(store: SQLiteKnowledgeStore) -> set[str]:
    """Return all non-system index names on knowledge_objects table."""
    conn = store.conn_manager.get_connection()
    rows = conn.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'index'
          AND tbl_name = 'knowledge_objects'
          AND name NOT LIKE 'sqlite_%'
        """
    ).fetchall()

    return {row[0] for row in rows}


# =============================================================================
# Index Creation Tests
# =============================================================================


class TestMetadataIndexCreation:
    """Tests for metadata index creation."""

    def test_default_indexes_exist(self, store: SQLiteKnowledgeStore) -> None:
        """Store initialization creates expected metadata indexes."""
        index_names = _get_index_names(store)

        expected = {
            "idx_knowledge_identity",
            "idx_knowledge_content_hash",
            "idx_source_identity",
            "idx_published_at",
            "idx_created_at",
            "idx_updated_at",
            "idx_recent_by_source",
            "idx_knowledge_deleted_at",
        }

        assert expected.issubset(index_names)

    def test_ensure_metadata_indexes_idempotent(self, store: SQLiteKnowledgeStore) -> None:
        """ensure_metadata_indexes does not fail when indexes already exist."""
        created = store.ensure_metadata_indexes()
        assert created == 0

    def test_ensure_metadata_indexes_recreates_missing_index(
        self, store: SQLiteKnowledgeStore
    ) -> None:
        """ensure_metadata_indexes recreates a dropped index."""
        conn = store._conn_manager.get_connection()
        conn.execute("DROP INDEX idx_knowledge_deleted_at")
        conn.commit()

        created = store.ensure_metadata_indexes()
        assert created == 1

        index_names = _get_index_names(store)
        assert "idx_knowledge_deleted_at" in index_names

    def test_list_metadata_indexes(self, store: SQLiteKnowledgeStore) -> None:
        """list_metadata_indexes returns sorted index names."""
        indexes = store.list_metadata_indexes()

        assert isinstance(indexes, list)
        assert len(indexes) > 0
        assert indexes == sorted(indexes)
        assert "idx_knowledge_identity" in indexes

    def test_optimize_metadata_indexes_runs_analyze(self, store: SQLiteKnowledgeStore) -> None:
        """optimize_metadata_indexes should not raise."""
        store.optimize_metadata_indexes()


# =============================================================================
# Metadata Query Tests
# =============================================================================


class TestQueryByMetadata:
    """Tests for query_by_metadata and related helpers."""

    def test_query_by_source_type(self, store: SQLiteKnowledgeStore) -> None:
        """query_by_source filters by source_type."""
        ko1 = _make_ko(external_id="1", source_type="rss", source_name="cnn")
        ko2 = _make_ko(external_id="2", source_type="rss", source_name="bbc")
        ko3 = _make_ko(external_id="3", source_type="github", source_name="repo")
        store.save_objects([ko1, ko2, ko3])

        results = store.query_by_source("rss")
        assert len(results) == 2

        source_types = {obj.source_type for obj in results}
        assert source_types == {"rss"}

    def test_query_by_source_name(self, store: SQLiteKnowledgeStore) -> None:
        """query_by_source filters by source_type and source_name."""
        ko1 = _make_ko(external_id="1", source_type="rss", source_name="cnn")
        ko2 = _make_ko(external_id="2", source_type="rss", source_name="bbc")
        store.save_objects([ko1, ko2])

        results = store.query_by_source("rss", "cnn")
        assert len(results) == 1
        assert results[0].source_name == "cnn"

    def test_query_limit_and_offset(self, store: SQLiteKnowledgeStore) -> None:
        """query_by_metadata respects limit and offset."""
        objects = [
            _make_ko(
                external_id=f"ext_{i}",
                content=f"Content {i}",
                published_at=datetime(2025, 1, 1, tzinfo=timezone.utc) + timedelta(hours=i),
            )
            for i in range(10)
        ]
        store.save_objects(objects)

        first_page = store.query_by_metadata(limit=3, offset=0)
        second_page = store.query_by_metadata(limit=3, offset=3)

        assert len(first_page) == 3
        assert len(second_page) == 3

        first_ids = {obj.external_id for obj in first_page}
        second_ids = {obj.external_id for obj in second_page}
        assert first_ids.isdisjoint(second_ids)

    def test_query_date_range(self, store: SQLiteKnowledgeStore) -> None:
        """query_by_metadata filters by published_at range."""
        now = datetime.now(timezone.utc)

        old = _make_ko(
            external_id="old",
            published_at=now - timedelta(days=30),
        )
        recent = _make_ko(
            external_id="recent",
            published_at=now - timedelta(days=1),
        )

        store.save_objects([old, recent])

        results = store.query_by_metadata(
            published_after=now - timedelta(days=7),
            published_before=now,
        )

        assert len(results) == 1
        assert results[0].external_id == "recent"

    def test_query_recent_orders_by_published_desc(self, store: SQLiteKnowledgeStore) -> None:
        """query_recent returns newest published objects first."""
        now = datetime.now(timezone.utc)

        obj1 = _make_ko(
            external_id="oldest",
            published_at=now - timedelta(days=3),
        )
        obj2 = _make_ko(
            external_id="newest",
            published_at=now - timedelta(days=1),
        )
        obj3 = _make_ko(
            external_id="middle",
            published_at=now - timedelta(days=2),
        )

        store.save_objects([obj1, obj2, obj3])

        results = store.query_recent(limit=10)

        external_ids = [obj.external_id for obj in results]
        assert external_ids == ["newest", "middle", "oldest"]

    def test_query_excludes_soft_deleted_by_default(self, store: SQLiteKnowledgeStore) -> None:
        """Soft-deleted objects are excluded by default."""
        ko = _make_ko()
        store.save_objects([ko])

        store.delete_by_id(ko.id)

        results = store.query_by_metadata()
        assert len(results) == 0

    def test_query_includes_soft_deleted_when_requested(self, store: SQLiteKnowledgeStore) -> None:
        """Soft-deleted objects are included when include_deleted=True."""
        ko = _make_ko()
        store.save_objects([ko])

        store.delete_by_id(ko.id)

        results = store.query_by_metadata(include_deleted=True)
        assert len(results) == 1
        assert results[0].id == ko.id

    def test_query_zero_limit_returns_empty(self, store: SQLiteKnowledgeStore) -> None:
        """limit <= 0 returns empty list."""
        ko = _make_ko()
        store.save_objects([ko])

        assert store.query_by_metadata(limit=0) == []
        assert store.query_by_metadata(limit=-1) == []

    def test_query_negative_offset_raises(self, store: SQLiteKnowledgeStore) -> None:
        """Negative offset raises ValueError."""
        with pytest.raises(ValueError, match="offset must be non-negative"):
            store.query_by_metadata(offset=-1)


# =============================================================================
# Performance Smoke Test
# =============================================================================


class TestMetadataQueryPerformance:
    """Lightweight performance smoke tests for metadata queries."""

    def test_query_performance_smoke(self, store: SQLiteKnowledgeStore) -> None:
        """Metadata query over hundreds of objects remains fast."""
        objects = [
            _make_ko(
                external_id=f"ext_{i}",
                source_type="rss",
                source_name="bulk_source",
                content=f"Bulk content {i}",
                published_at=datetime(2025, 1, 1, tzinfo=timezone.utc) + timedelta(minutes=i),
            )
            for i in range(500)
        ]

        store.save_objects(objects)

        start = time.perf_counter()
        results = store.query_by_source(
            source_type="rss",
            source_name="bulk_source",
            limit=100,
        )
        elapsed = time.perf_counter() - start

        assert len(results) == 100
        assert elapsed < 2.0
