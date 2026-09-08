"""Knowledge Delete Service.

High-level delete operations with retention policy
and cross-storage cleanup support.

Default behavior: soft-delete (set deleted_at).
Hard-delete only when permanent=True or via retention policy.
"""

from datetime import datetime, timedelta, timezone
from typing import Any

from app.core.logger import get_logger
from app.storage.knowledge.sqlite_store import SQLiteKnowledgeStore

logger = get_logger(__name__)


class KnowledgeDeleteService:
    """High-level delete operations for KnowledgeObjects.

    Default behavior is soft-delete: objects are marked with deleted_at
    timestamp instead of being removed. This supports undo/restore in
    future (INFRA-002 Web Dashboard).

    Hard-delete is available via permanent=True or retention policy.

    Args:
        store: SQLiteKnowledgeStore instance.
    """

    def __init__(self, store: SQLiteKnowledgeStore) -> None:
        self._store = store

    def delete_by_id(self, obj_id: str, permanent: bool = False) -> bool:
        """Delete a KnowledgeObject by ID.

        Args:
            obj_id: The internal UUID of the object.
            permanent: If True, hard-delete. Default: soft-delete.

        Returns:
            True if deleted, False if not found.
        """
        return self._store.delete_by_id(obj_id, permanent=permanent)

    def delete_by_source(self, source_type: str, source_name: str, permanent: bool = False) -> int:
        """Delete all KnowledgeObjects from a specific source.

        Args:
            source_type: The source type (e.g., "rss", "github").
            source_name: The source name (e.g., "techcrunch").
            permanent: If True, hard-delete. Default: soft-delete.

        Returns:
            Number of objects deleted.
        """
        return self._store.delete_by_source(source_type, source_name, permanent=permanent)

    def apply_retention_policy(self, days: int) -> int:
        """Apply retention policy: hard-delete soft-deleted objects older than N days.

        This permanently removes objects that have been soft-deleted
        for more than the specified retention period.

        Args:
            days: Retention period in days. Soft-deleted objects with
                  deleted_at older than (now - days) are hard-deleted.

        Returns:
            Number of objects permanently deleted.

        Raises:
            ValueError: If days is negative.
        """
        if days < 0:
            raise ValueError(f"Retention days must be non-negative, got {days}")

        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        purged_count = self._store.purge_expired_trash(cutoff)

        logger.info(
            "Retention policy applied: purged %d expired soft-deleted objects "
            "(deleted_at older than %d days)",
            purged_count,
            days,
        )

        return purged_count

    def cleanup_orphaned_vectors(self, vector_sync_service: Any | None = None) -> int:
        """Cleanup orphaned vectors in Vector Store.

        When Vector Store is implemented, this method will delete
        vectors that no longer have corresponding KnowledgeObjects.

        Returns:
            Number of orphaned vectors cleaned up.
        """
        if vector_sync_service is None:
            logger.info(
                "cleanup_orphaned_vectors: VectorSyncService not provided. No vectors cleaned up."
            )
            return 0

        # Get all active (non-deleted) KnowledgeObject IDs from SQLite
        all_objects = self._store.get_all()
        valid_ids = {obj.id for obj in all_objects}

        logger.info(
            "cleanup_orphaned_vectors: Found %d active KnowledgeObjects",
            len(valid_ids),
        )

        # Delegate to VectorSyncService
        return vector_sync_service.delete_orphaned_vectors(valid_ids)  # type: ignore[no-any-return]
