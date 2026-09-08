"""Unit tests for KnowledgeDeleteService."""

from collections.abc import Generator
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from app.core.utils import compute_text_hash
from app.models.knowledge_object import KnowledgeObject
from app.models.metadata import ExtractionResult
from app.services.knowledge.delete_service import KnowledgeDeleteService
from app.storage.knowledge.sqlite_store import SQLiteKnowledgeStore

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "test_delete_service.db"


@pytest.fixture
def store(db_path: Path) -> Generator[SQLiteKnowledgeStore, Any, None]:
    s = SQLiteKnowledgeStore(db_path=db_path)
    yield s
    s.close()


@pytest.fixture
def service(store: SQLiteKnowledgeStore) -> KnowledgeDeleteService:
    return KnowledgeDeleteService(store)


def _make_ko(
    external_id: str = "ext_001",
    source_type: str = "rss",
    source_name: str = "test_source",
    content: str = "Test content.",
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
        "title": "Test Title",
        "content_text": content,
        "metadata": metadata,
    }
    if created_at is not None:
        kwargs["created_at"] = created_at
    return KnowledgeObject(**kwargs)


# =============================================================================
# delete_by_id Tests
# =============================================================================


class TestServiceDeleteById:
    def test_soft_delete_default(
        self, store: SQLiteKnowledgeStore, service: KnowledgeDeleteService
    ) -> None:
        ko = _make_ko()
        store.save_objects([ko])

        result = service.delete_by_id(ko.id)
        assert result is True
        assert store.count() == 0
        # Still in DB (soft-deleted)
        assert store.get_by_id(ko.id, include_deleted=True) is not None

    def test_hard_delete(
        self, store: SQLiteKnowledgeStore, service: KnowledgeDeleteService
    ) -> None:
        ko = _make_ko()
        store.save_objects([ko])

        result = service.delete_by_id(ko.id, permanent=True)
        assert result is True
        assert store.get_by_id(ko.id, include_deleted=True) is None


# =============================================================================
# apply_retention_policy Tests
# =============================================================================


class TestApplyRetentionPolicy:
    def test_purges_expired_soft_deleted(
        self, store: SQLiteKnowledgeStore, service: KnowledgeDeleteService
    ) -> None:
        """Retention policy hard-deletes soft-deleted objects past retention."""
        ko = _make_ko()
        store.save_objects([ko])

        # Soft-delete
        service.delete_by_id(ko.id)
        assert store.count() == 0

        # Manually backdate deleted_at to 100 days ago
        conn = store._conn_manager.get_connection()
        old_deleted_at = (datetime.now(timezone.utc) - timedelta(days=100)).isoformat()
        conn.execute(
            "UPDATE knowledge_objects SET deleted_at = ? WHERE id = ?",
            (old_deleted_at, ko.id),
        )
        conn.commit()

        # Apply 30-day retention
        purged = service.apply_retention_policy(days=30)
        assert purged == 1
        assert store.get_by_id(ko.id, include_deleted=True) is None

    def test_does_not_purge_recent_soft_deleted(
        self, store: SQLiteKnowledgeStore, service: KnowledgeDeleteService
    ) -> None:
        ko = _make_ko()
        store.save_objects([ko])

        service.delete_by_id(ko.id)  # deleted_at = now

        purged = service.apply_retention_policy(days=30)
        assert purged == 0
        assert store.get_by_id(ko.id, include_deleted=True) is not None

    def test_does_not_purge_active_objects(
        self, store: SQLiteKnowledgeStore, service: KnowledgeDeleteService
    ) -> None:
        ko = _make_ko()
        store.save_objects([ko])

        purged = service.apply_retention_policy(days=0)
        assert purged == 0
        assert store.count() == 1

    def test_negative_days_raises(self, service: KnowledgeDeleteService) -> None:
        with pytest.raises(ValueError, match="non-negative"):
            service.apply_retention_policy(days=-1)


# =============================================================================
# cleanup_orphaned_vectors Tests
# =============================================================================


class TestCleanupOrphanedVectors:
    def test_returns_zero(self, service: KnowledgeDeleteService) -> None:
        assert service.cleanup_orphaned_vectors() == 0

    def test_does_not_affect_store(
        self, store: SQLiteKnowledgeStore, service: KnowledgeDeleteService
    ) -> None:
        ko = _make_ko()
        store.save_objects([ko])

        service.cleanup_orphaned_vectors()
        assert store.count() == 1
