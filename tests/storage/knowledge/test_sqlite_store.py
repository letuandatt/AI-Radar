"""Unit tests for SQLiteKnowledgeStore with idempotent semantics (DATA-001).

Covers:
- Schema initialization
- Idempotent save (created / updated / skipped)
- Lookup by external_id and content_hash
- Concurrent writes safety
- Circuit breaker behavior
- Retry logic
"""

import sqlite3
import threading
from collections.abc import Generator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from app.core.utils import compute_text_hash
from app.models.knowledge_object import KnowledgeObject
from app.models.metadata import ExtractionResult
from app.storage.knowledge.base import CircuitBreaker, CircuitBreakerOpenError
from app.storage.knowledge.knowledge_store import SaveResult
from app.storage.knowledge.sqlite_store import SQLiteKnowledgeStore

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """Provide a temporary database path."""
    return tmp_path / "test_knowledge.db"


@pytest.fixture
def store(db_path: Path) -> Generator[SQLiteKnowledgeStore, Any, None]:
    """Provide a SQLiteKnowledgeStore instance."""
    s = SQLiteKnowledgeStore(db_path=db_path)
    yield s
    s.close()


@pytest.fixture
def sample_metadata() -> ExtractionResult:
    """Provide a valid ExtractionResult."""
    return ExtractionResult(
        summary="A concise summary about AI research.",
        topics=["AI", "Machine Learning"],
        entities=["OpenAI"],
        relevance_score=0.9,
    )


def _make_knowledge_object(
    external_id: str = "ext_001",
    source_type: str = "rss",
    source_name: str = "test_source",
    content: str = "Test content for knowledge object.",
    title: str = "Test Title",
    metadata: ExtractionResult | None = None,
) -> KnowledgeObject:
    """Helper to create a KnowledgeObject with sensible defaults."""
    if metadata is None:
        metadata = ExtractionResult(
            summary="A concise summary.",
            topics=["AI"],
            entities=["OpenAI"],
            relevance_score=0.9,
        )
    return KnowledgeObject(
        source_type=source_type,
        source_name=source_name,
        external_id=external_id,
        source_url=f"https://example.com/{external_id}",
        content_hash=compute_text_hash(content),
        fetched_at=datetime(2025, 1, 2, 10, 0, 0, tzinfo=timezone.utc),
        published_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        title=title,
        content_text=content,
        metadata=metadata,
    )


# =============================================================================
# Schema Tests
# =============================================================================


class TestSchemaInitialization:
    """Tests for schema creation."""

    def test_schema_created_on_init(self, db_path: Path) -> None:
        """Table is created when store is initialized."""
        store = SQLiteKnowledgeStore(db_path=db_path)
        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='knowledge_objects'"
        )
        assert cursor.fetchone() is not None
        conn.close()
        store.close()

    def test_indexes_created_on_init(self, db_path: Path) -> None:
        """Indexes are created when store is initialized."""
        store = SQLiteKnowledgeStore(db_path=db_path)
        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%'"
        )
        indexes = [row[0] for row in cursor.fetchall()]
        conn.close()
        store.close()

        assert "idx_knowledge_identity" in indexes
        assert "idx_knowledge_content_hash" in indexes
        assert "idx_source_identity" in indexes
        assert "idx_published_at" in indexes
        assert "idx_created_at" in indexes
        assert "idx_updated_at" in indexes

    def test_schema_idempotent(self, db_path: Path) -> None:
        """Re-initializing store does not fail or duplicate schema."""
        store1 = SQLiteKnowledgeStore(db_path=db_path)
        store1.close()
        # Second init should not raise
        store2 = SQLiteKnowledgeStore(db_path=db_path)
        assert store2.count() == 0
        store2.close()


# =============================================================================
# Basic CRUD Tests
# =============================================================================


class TestBasicOperations:
    """Tests for basic store operations."""

    def test_empty_store(self, store: SQLiteKnowledgeStore) -> None:
        assert store.count() == 0
        assert store.get_all() == []

    def test_save_and_retrieve(self, store: SQLiteKnowledgeStore) -> None:
        obj = _make_knowledge_object()
        result = store.save_objects([obj])

        assert result.created == 1
        assert result.updated == 0
        assert result.skipped == 0
        assert store.count() == 1

        retrieved = store.get_by_external_id("ext_001", "rss")
        assert retrieved is not None
        assert retrieved.title == "Test Title"
        assert retrieved.source_name == "test_source"

    def test_get_by_content_hash(self, store: SQLiteKnowledgeStore) -> None:
        obj = _make_knowledge_object(content="Unique content here")
        store.save_objects([obj])

        found = store.get_by_content_hash(compute_text_hash("Unique content here"))
        assert found is not None
        assert found.external_id == "ext_001"

    def test_get_by_content_hash_not_found(self, store: SQLiteKnowledgeStore) -> None:
        result = store.get_by_content_hash("nonexistent_hash")
        assert result is None

    def test_get_by_external_id_not_found(self, store: SQLiteKnowledgeStore) -> None:
        result = store.get_by_external_id("nonexistent", "rss")
        assert result is None

    def test_get_all_returns_all_objects(self, store: SQLiteKnowledgeStore) -> None:
        objs = [
            _make_knowledge_object(external_id=f"ext_{i}", content=f"Content {i}") for i in range(5)
        ]
        store.save_objects(objs)

        all_objs = store.get_all()
        assert len(all_objs) == 5

    def test_metadata_round_trip(self, store: SQLiteKnowledgeStore) -> None:
        """Metadata JSON serialization/deserialization works correctly."""
        metadata = ExtractionResult(
            summary="Test summary with special chars: <>&\"'",
            topics=["AI", "NLP", "Computer Vision"],
            entities=["OpenAI", "Google DeepMind"],
            relevance_score=0.85,
        )
        obj = _make_knowledge_object(metadata=metadata)
        store.save_objects([obj])

        retrieved = store.get_by_external_id("ext_001", "rss")
        assert retrieved is not None
        assert retrieved.metadata.summary == metadata.summary
        assert retrieved.metadata.topics == metadata.topics
        assert retrieved.metadata.entities == metadata.entities
        assert retrieved.metadata.relevance_score == metadata.relevance_score


# =============================================================================
# DATA-001 Idempotency Tests
# =============================================================================


class TestIdempotency:
    """Tests for idempotent save behavior (DATA-001)."""

    def test_first_save_creates_all(self, store: SQLiteKnowledgeStore) -> None:
        """First call: all objects are new → all created."""
        objs = [
            _make_knowledge_object(external_id=f"id_{i}", content=f"Content {i}") for i in range(5)
        ]
        result = store.save_objects(objs)

        assert result.created == 5
        assert result.updated == 0
        assert result.skipped == 0
        assert store.count() == 5

    def test_second_save_same_objects_skips_all(self, store: SQLiteKnowledgeStore) -> None:
        """Second call with same objects: all skipped → 0 created."""
        objs = [
            _make_knowledge_object(external_id=f"id_{i}", content=f"Content {i}") for i in range(5)
        ]
        store.save_objects(objs)
        result = store.save_objects(objs)

        assert result.created == 0
        assert result.updated == 0
        assert result.skipped == 5
        assert store.count() == 5

    def test_changed_content_triggers_update(self, store: SQLiteKnowledgeStore) -> None:
        """Object with different content_hash → UPDATE."""
        obj_v1 = _make_knowledge_object(external_id="a", content="Original content")
        store.save_objects([obj_v1])

        # Same identity, different content
        obj_v2 = _make_knowledge_object(external_id="a", content="Updated content")
        result = store.save_objects([obj_v2])

        assert result.created == 0
        assert result.updated == 1
        assert result.skipped == 0
        assert store.count() == 1  # Still 1, not duplicated

        # Verify content was actually updated
        retrieved = store.get_by_external_id("a", "rss")
        assert retrieved is not None
        assert retrieved.content_text == "Updated content"

    def test_mixed_batch(self, store: SQLiteKnowledgeStore) -> None:
        """Batch with new, unchanged, and changed objects."""
        # Initial save
        obj_a = _make_knowledge_object(external_id="a", content="Content A")
        obj_b = _make_knowledge_object(external_id="b", content="Content B")
        store.save_objects([obj_a, obj_b])

        # Mixed batch: a changed, b unchanged, c new
        obj_a_modified = _make_knowledge_object(external_id="a", content="Content A v2")
        obj_c = _make_knowledge_object(external_id="c", content="Content C")

        result = store.save_objects([obj_a_modified, obj_b, obj_c])

        assert result.created == 1  # c is new
        assert result.updated == 1  # a was changed
        assert result.skipped == 1  # b unchanged
        assert store.count() == 3

    def test_same_identity_different_source_type(self, store: SQLiteKnowledgeStore) -> None:
        """Same external_id but different source_type → different objects."""
        obj_rss = _make_knowledge_object(external_id="123", source_type="rss", source_name="feed_a")
        obj_gh = _make_knowledge_object(
            external_id="123", source_type="github", source_name="repo_b"
        )

        result = store.save_objects([obj_rss, obj_gh])
        assert result.created == 2
        assert store.count() == 2

    def test_save_result_dataclass(self, store: SQLiteKnowledgeStore) -> None:
        """SaveResult has correct properties."""
        result = SaveResult(created=3, updated=1, skipped=2)
        assert result.total_processed == 6


# =============================================================================
# Concurrency Tests
# =============================================================================


class TestConcurrency:
    """Tests for concurrent write safety."""

    def test_concurrent_writes_no_corruption(self, db_path: Path) -> None:
        """Multiple threads writing simultaneously don't corrupt database."""
        store = SQLiteKnowledgeStore(db_path=db_path)
        errors: list[Exception] = []

        def writer(thread_id: int) -> None:
            try:
                objs = [
                    _make_knowledge_object(
                        external_id=f"thread_{thread_id}_obj_{i}",
                        content=f"Thread {thread_id} content {i}",
                    )
                    for i in range(10)
                ]
                store.save_objects(objs)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Errors during concurrent writes: {errors}"
        assert store.count() == 30  # 3 threads × 10 objects
        store.close()


# =============================================================================
# Circuit Breaker Tests
# =============================================================================


class TestCircuitBreaker:
    """Tests for circuit breaker behavior (GAP-003)."""

    def test_circuit_opens_after_failures(self, db_path: Path) -> None:
        """Circuit opens after consecutive failed save operations."""
        from unittest.mock import patch

        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=60.0)
        store = SQLiteKnowledgeStore(db_path=db_path, circuit_breaker=cb)

        try:
            with patch.object(
                store,
                "_save_objects_with_retry",
                side_effect=sqlite3.OperationalError("database locked"),
            ):
                # First failed operation
                with pytest.raises(sqlite3.OperationalError):
                    store.save_objects([_make_knowledge_object(external_id="c1")])

                # Second failed operation -> circuit opens
                with pytest.raises(sqlite3.OperationalError):
                    store.save_objects([_make_knowledge_object(external_id="c2")])

                # Third operation -> circuit is open
                with pytest.raises(CircuitBreakerOpenError):
                    store.save_objects([_make_knowledge_object(external_id="c3")])
        finally:
            store.close()

    def test_circuit_resets_on_success(self, db_path: Path) -> None:
        """Circuit resets after successful operation."""
        cb = CircuitBreaker(failure_threshold=5)
        store = SQLiteKnowledgeStore(db_path=db_path, circuit_breaker=cb)

        # Successful operation
        store.save_objects([_make_knowledge_object()])
        assert cb.state == CircuitBreaker.CLOSED
        store.close()


# =============================================================================
# Edge Case Tests
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_empty_batch(self, store: SQLiteKnowledgeStore) -> None:
        """Saving empty list returns zero counts."""
        result = store.save_objects([])
        assert result.created == 0
        assert result.updated == 0
        assert result.skipped == 0

    def test_large_batch(self, store: SQLiteKnowledgeStore) -> None:
        """Large batch saves correctly."""
        objs = [
            _make_knowledge_object(external_id=f"obj_{i}", content=f"Content {i}")
            for i in range(100)
        ]
        result = store.save_objects(objs)
        assert result.created == 100
        assert store.count() == 100

    def test_store_close_and_reopen(self, db_path: Path) -> None:
        """Data persists across store instances."""
        store1 = SQLiteKnowledgeStore(db_path=db_path)
        store1.save_objects([_make_knowledge_object()])
        store1.close()

        store2 = SQLiteKnowledgeStore(db_path=db_path)
        assert store2.count() == 1
        retrieved = store2.get_by_external_id("ext_001", "rss")
        assert retrieved is not None
        store2.close()

    def test_null_published_at(self, store: SQLiteKnowledgeStore) -> None:
        """Object with None published_at saves correctly."""
        obj = _make_knowledge_object()
        obj.published_at = None  # type: ignore[assignment]
        store.save_objects([obj])

        retrieved = store.get_by_external_id("ext_001", "rss")
        assert retrieved is not None
        assert retrieved.published_at is None
