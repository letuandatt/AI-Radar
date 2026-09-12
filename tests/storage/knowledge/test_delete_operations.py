"""Unit tests for SQLiteKnowledgeStore delete operations.

Covers both soft-delete (default) and hard-delete (permanent=True).
"""

from collections.abc import Generator
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from app.core.utils import compute_text_hash
from app.models.knowledge_object import KnowledgeObject
from app.models.metadata import ExtractionResult
from app.storage.knowledge import SQLiteKnowledgeStore

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "test_delete.db"


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
    created_at: datetime | None = None,
) -> KnowledgeObject:
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
        "published_at": datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        "title": title,
        "content_text": content,
        "metadata": metadata,
    }
    if created_at is not None:
        kwargs["created_at"] = created_at
    return KnowledgeObject(**kwargs)


# =============================================================================
# Soft-delete by ID Tests
# =============================================================================


class TestSoftDeleteById:
    """Tests for soft-delete (default) via delete_by_id."""

    def test_soft_delete_default(self, store: SQLiteKnowledgeStore) -> None:
        """delete_by_id defaults to soft-delete."""
        ko = _make_ko()
        store.save_objects([ko])
        assert store.count() == 1

        result = store.delete_by_id(ko.id)
        assert result is True
        assert store.count() == 0  # Filtered from count

        # Object still exists in DB but with deleted_at set
        deleted_obj = store.get_by_id(ko.id, include_deleted=True)
        assert deleted_obj is not None

    def test_soft_delete_hidden_from_get(self, store: SQLiteKnowledgeStore) -> None:
        """Soft-deleted object hidden from get_by_id by default."""
        ko = _make_ko()
        store.save_objects([ko])

        store.delete_by_id(ko.id)

        # Default get_by_id should not find it
        assert store.get_by_id(ko.id) is None
        # include_deleted=True should find it
        assert store.get_by_id(ko.id, include_deleted=True) is not None

    def test_soft_delete_hidden_from_external_id(self, store: SQLiteKnowledgeStore) -> None:
        """Soft-deleted object hidden from get_by_external_id."""
        ko = _make_ko()
        store.save_objects([ko])

        store.delete_by_id(ko.id)

        assert store.get_by_external_id(ko.external_id, ko.source_type) is None

    def test_soft_delete_hidden_from_content_hash(self, store: SQLiteKnowledgeStore) -> None:
        """Soft-deleted object hidden from get_by_content_hash."""
        ko = _make_ko()
        store.save_objects([ko])

        store.delete_by_id(ko.id)

        assert store.get_by_content_hash(ko.content_hash) is None

    def test_soft_delete_idempotent(self, store: SQLiteKnowledgeStore) -> None:
        """Soft-deleting an already soft-deleted object returns False."""
        ko = _make_ko()
        store.save_objects([ko])

        assert store.delete_by_id(ko.id) is True
        # Second soft-delete: already deleted, WHERE deleted_at IS NULL matches nothing
        assert store.delete_by_id(ko.id) is False


# =============================================================================
# Hard-delete by ID Tests
# =============================================================================


class TestHardDeleteById:
    """Tests for hard-delete via delete_by_id(permanent=True)."""

    def test_hard_delete_removes_row(self, store: SQLiteKnowledgeStore) -> None:
        """permanent=True removes row completely."""
        ko = _make_ko()
        store.save_objects([ko])

        result = store.delete_by_id(ko.id, permanent=True)
        assert result is True
        assert store.count() == 0

        # Even include_deleted=True should not find it
        assert store.get_by_id(ko.id, include_deleted=True) is None

    def test_hard_delete_nonexistent(self, store: SQLiteKnowledgeStore) -> None:
        """Hard-delete non-existent ID returns False."""
        result = store.delete_by_id("nonexistent", permanent=True)
        assert result is False


# =============================================================================
# Soft-delete by Source Tests
# =============================================================================


class TestSoftDeleteBySource:
    """Tests for delete_by_source with soft-delete default."""

    def test_soft_delete_source(self, store: SQLiteKnowledgeStore) -> None:
        ko1 = _make_ko(external_id="1", source_type="rss", source_name="cnn")
        ko2 = _make_ko(external_id="2", source_type="rss", source_name="cnn")
        ko3 = _make_ko(external_id="3", source_type="github", source_name="repo1")
        store.save_objects([ko1, ko2, ko3])

        deleted = store.delete_by_source("rss", "cnn")
        assert deleted == 2
        assert store.count() == 1

        # ko1, ko2 hidden from get
        assert store.get_by_external_id("1", "rss") is None
        assert store.get_by_external_id("2", "rss") is None
        # ko3 still visible
        assert store.get_by_external_id("3", "github") is not None

    def test_hard_delete_source(self, store: SQLiteKnowledgeStore) -> None:
        ko = _make_ko(source_type="rss", source_name="cnn")
        store.save_objects([ko])

        deleted = store.delete_by_source("rss", "cnn", permanent=True)
        assert deleted == 1
        assert store.get_by_id(ko.id, include_deleted=True) is None


# =============================================================================
# delete_older_than Tests
# =============================================================================


class TestDeleteOlderThan:
    """Tests for delete_older_than (hard-delete default)."""

    def test_hard_delete_default(self, store: SQLiteKnowledgeStore) -> None:
        """delete_older_than defaults to hard-delete."""
        now = datetime.now(timezone.utc)
        old_ko = _make_ko(external_id="old", created_at=now - timedelta(days=30))
        recent_ko = _make_ko(external_id="recent", created_at=now - timedelta(days=5))
        store.save_objects([old_ko, recent_ko])

        cutoff = now - timedelta(days=10)
        deleted = store.delete_older_than(cutoff)
        assert deleted == 1
        assert store.count() == 1

        # Old object completely gone
        assert store.get_by_id(old_ko.id, include_deleted=True) is None

    def test_soft_delete_option(self, store: SQLiteKnowledgeStore) -> None:
        """delete_older_than with permanent=False soft-deletes."""
        now = datetime.now(timezone.utc)
        old_ko = _make_ko(external_id="old", created_at=now - timedelta(days=30))
        store.save_objects([old_ko])

        cutoff = now - timedelta(days=10)
        deleted = store.delete_older_than(cutoff, permanent=False)
        assert deleted == 1
        assert store.count() == 0

        # Object still in DB but soft-deleted
        assert store.get_by_id(old_ko.id, include_deleted=True) is not None

    def test_delete_older_than_none(self, store: SQLiteKnowledgeStore) -> None:
        ko = _make_ko()
        store.save_objects([ko])

        cutoff = datetime(2020, 1, 1, tzinfo=timezone.utc)
        deleted = store.delete_older_than(cutoff)
        assert deleted == 0
        assert store.count() == 1


# =============================================================================
# purge_expired_trash Tests
# =============================================================================


class TestPurgeExpiredTrash:
    """Tests for purge_expired_trash (retention policy support)."""

    def test_purge_expired_soft_deleted(self, store: SQLiteKnowledgeStore) -> None:
        """Purge soft-deleted objects whose deleted_at is older than cutoff."""
        ko = _make_ko()
        store.save_objects([ko])

        # Soft-delete
        store.delete_by_id(ko.id)
        assert store.count() == 0

        # Manually set deleted_at to 100 days ago
        conn = store._conn_manager.get_connection()
        old_deleted_at = (datetime.now(timezone.utc) - timedelta(days=100)).isoformat()
        conn.execute(
            "UPDATE knowledge_objects SET deleted_at = ? WHERE id = ?",
            (old_deleted_at, ko.id),
        )
        conn.commit()

        # Purge with 30-day cutoff
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        purged = store.purge_expired_trash(cutoff)
        assert purged == 1

        # Completely gone
        assert store.get_by_id(ko.id, include_deleted=True) is None

    def test_purge_does_not_affect_active(self, store: SQLiteKnowledgeStore) -> None:
        """Purge does not affect non-deleted objects."""
        ko = _make_ko()
        store.save_objects([ko])

        cutoff = datetime(2020, 1, 1, tzinfo=timezone.utc)
        purged = store.purge_expired_trash(cutoff)
        assert purged == 0
        assert store.count() == 1

    def test_purge_does_not_affect_recent_soft_deleted(self, store: SQLiteKnowledgeStore) -> None:
        """Purge does not affect recently soft-deleted objects."""
        ko = _make_ko()
        store.save_objects([ko])

        store.delete_by_id(ko.id)  # deleted_at = now

        # Purge with 30-day cutoff — recently deleted should NOT be purged
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        purged = store.purge_expired_trash(cutoff)
        assert purged == 0

        # Still in DB (soft-deleted)
        assert store.get_by_id(ko.id, include_deleted=True) is not None
