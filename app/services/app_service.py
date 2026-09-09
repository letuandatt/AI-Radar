"""Application Service — Facade for the Knowledge Repository.

This is the single entry point for all repository interactions from
the application layer (pipelines, scheduler, future API, MCP adapter).

Implements graceful degradation:
- SQLite is the source of truth — MUST succeed
- Qdrant sync is retried 3x — warns and continues on failure
- BM25 update is retried 2x — warns and continues on failure
"""

import time
from dataclasses import dataclass

from app.core.logger import get_logger
from app.models.knowledge_object import KnowledgeObject
from app.services.embedding.context_builder import ContextBuilder
from app.services.repository.access_service import RepositoryAccessService
from app.services.repository.initializer import RepositoryInitializer
from app.services.repository.lifecycle_service import RepositoryLifecycleService
from app.services.repository.query_models import (
    KnowledgeListResponse,
    KnowledgeQuery,
    RepositoryStatistics,
)
from app.services.vector.sync_service import VectorSyncService
from app.storage.search.bm25_index import BM25Document

logger = get_logger(__name__)

# Retry configuration
QDRANT_MAX_RETRIES = 3
QDRANT_RETRY_BASE_DELAY = 0.5
BM25_MAX_RETRIES = 2
BM25_RETRY_BASE_DELAY = 0.3


# =============================================================================
# Result Model
# =============================================================================


@dataclass(frozen=True)
class ApplicationSaveResult:
    """Result of save_objects() across all three storage layers.

    Attributes:
        sqlite_created: Number of new objects created in SQLite.
        sqlite_updated: Number of existing objects updated in SQLite.
        sqlite_skipped: Number of objects skipped (no change).
        qdrant_synced: Number of vectors successfully synced to Qdrant.
        qdrant_failed: Number of vectors that failed to sync.
        bm25_synced: Number of documents successfully added to BM25.
        bm25_failed: Number of documents that failed BM25 update.
    """

    sqlite_created: int
    sqlite_updated: int
    sqlite_skipped: int
    qdrant_synced: int
    qdrant_failed: int
    bm25_synced: int
    bm25_failed: int

    @property
    def sqlite_total(self) -> int:
        """Total objects processed by SQLite."""
        return self.sqlite_created + self.sqlite_updated + self.sqlite_skipped

    @property
    def qdrant_total(self) -> int:
        """Total vectors attempted for Qdrant sync."""
        return self.qdrant_synced + self.qdrant_failed

    @property
    def bm25_total(self) -> int:
        """Total documents attempted for BM25 update."""
        return self.bm25_synced + self.bm25_failed

    @property
    def is_fully_consistent(self) -> bool:
        """True if all three storages are fully aligned."""
        return self.qdrant_failed == 0 and self.bm25_failed == 0


# =============================================================================
# Application Service
# =============================================================================


class ApplicationService:
    """Facade for Knowledge Repository interactions.

    Provides a unified API for pipelines, scheduler, and future API layers
    to interact with the repository without knowing storage internals.

    Args:
        initializer: Initialized RepositoryInitializer with all stores.
        access_service: RepositoryAccessService for typed read operations.
        lifecycle_service: RepositoryLifecycleService for backup/restore.
    """

    def __init__(
        self,
        initializer: RepositoryInitializer,
        access_service: RepositoryAccessService,
        lifecycle_service: RepositoryLifecycleService,
    ) -> None:
        self._initializer = initializer
        self._access_service = access_service
        self._lifecycle_service = lifecycle_service

        # Build VectorSyncService from initializer components
        self._vector_sync = VectorSyncService(
            vector_store=initializer.qdrant_store,
        )
        self._context_builder = ContextBuilder()

    # ------------------------------------------------------------------
    # Write Operations
    # ------------------------------------------------------------------

    def save_objects(self, objects: list[KnowledgeObject]) -> ApplicationSaveResult:
        """Save KnowledgeObjects to all three storage layers.

        Strategy:
        1. SQLite (source of truth) — must succeed, raises on failure.
        2. Qdrant vectors — retry 3x with exponential backoff, warn on fail.
        3. BM25 keyword index — retry 2x, warn on fail.

        Args:
            objects: List of KnowledgeObjects to save.

        Returns:
            ApplicationSaveResult with counts per storage layer.

        Raises:
            Exception: If SQLite save fails (critical failure).
        """
        if not objects:
            return ApplicationSaveResult(
                sqlite_created=0,
                sqlite_updated=0,
                sqlite_skipped=0,
                qdrant_synced=0,
                qdrant_failed=0,
                bm25_synced=0,
                bm25_failed=0,
            )

        # Track pending writes for graceful shutdown (REL-001)
        self._lifecycle_service.track_write_start()
        try:
            return self._save_objects_internal(objects)
        finally:
            self._lifecycle_service.track_write_end()

    def _save_objects_internal(self, objects: list[KnowledgeObject]) -> ApplicationSaveResult:
        """Internal implementation of save_objects."""

        # Step 1: Save to SQLite (source of truth)
        sqlite_result = self._initializer.sqlite_store.save_objects(objects)
        logger.info(
            "SQLite save: %d created, %d updated, %d skipped",
            sqlite_result.created,
            sqlite_result.updated,
            sqlite_result.skipped,
        )

        # Only sync objects that were actually written (created or updated)
        objects_to_sync = [
            obj
            for obj in objects
            # Skip if content was unchanged
            if obj.content_hash is not None
        ]

        # Step 2: Sync vectors to Qdrant (with retry)
        qdrant_synced = 0
        qdrant_failed = 0
        embedding_provider = self._initializer.embedding_provider

        for obj in objects_to_sync:
            if self._sync_vector_with_retry(obj, embedding_provider):
                qdrant_synced += 1
            else:
                qdrant_failed += 1

        if qdrant_failed > 0:
            logger.warning(
                "Qdrant sync partial: %d synced, %d failed "
                "(vectors can be rebuilt via full_reindex)",
                qdrant_synced,
                qdrant_failed,
            )

        # Step 3: Update BM25 index (with retry)
        bm25_synced = 0
        bm25_failed = 0

        for obj in objects_to_sync:
            if self._update_bm25_with_retry(obj):
                bm25_synced += 1
            else:
                bm25_failed += 1

        if bm25_failed > 0:
            logger.warning(
                "BM25 update partial: %d synced, %d failed "
                "(BM25 can be rebuilt via IndexMaintenanceService)",
                bm25_synced,
                bm25_failed,
            )

        result = ApplicationSaveResult(
            sqlite_created=sqlite_result.created,
            sqlite_updated=sqlite_result.updated,
            sqlite_skipped=sqlite_result.skipped,
            qdrant_synced=qdrant_synced,
            qdrant_failed=qdrant_failed,
            bm25_synced=bm25_synced,
            bm25_failed=bm25_failed,
        )

        if result.is_fully_consistent:
            logger.info(
                "save_objects fully consistent: %d objects across all 3 stores",
                result.sqlite_total,
            )
        else:
            logger.warning(
                "save_objects partially consistent: sqlite=%d, qdrant=%d/%d, bm25=%d/%d",
                result.sqlite_total,
                result.qdrant_synced,
                result.qdrant_total,
                result.bm25_synced,
                result.bm25_total,
            )

        return result

    def _sync_vector_with_retry(
        self,
        obj: KnowledgeObject,
        embedding_provider: object,
    ) -> bool:
        """Sync a single object's vector to Qdrant with retry.

        Args:
            obj: KnowledgeObject to sync.
            embedding_provider: EmbeddingProvider instance.

        Returns:
            True if sync succeeded, False if all retries exhausted.
        """
        last_error: Exception | None = None

        for attempt in range(QDRANT_MAX_RETRIES):
            try:
                success = self._vector_sync.sync_knowledge_object(
                    obj,
                    embedding_provider,  # type: ignore[arg-type]
                )
                return success
            except Exception as e:
                last_error = e
                if attempt < QDRANT_MAX_RETRIES - 1:
                    delay = QDRANT_RETRY_BASE_DELAY * (2**attempt)
                    logger.debug(
                        "Qdrant sync attempt %d/%d failed for %s: %s. Retrying in %.1fs...",
                        attempt + 1,
                        QDRANT_MAX_RETRIES,
                        obj.id,
                        e,
                        delay,
                    )
                    time.sleep(delay)

        logger.warning(
            "Qdrant sync failed for %s after %d attempts: %s",
            obj.id,
            QDRANT_MAX_RETRIES,
            last_error,
        )
        return False

    def _update_bm25_with_retry(self, obj: KnowledgeObject) -> bool:
        """Update BM25 index for a single object with retry.

        Args:
            obj: KnowledgeObject to add to BM25 index.

        Returns:
            True if update succeeded, False if all retries exhausted.
        """
        last_error: Exception | None = None

        for attempt in range(BM25_MAX_RETRIES):
            try:
                text = f"{obj.title} {obj.content_text}"
                bm25_doc = BM25Document(
                    id=obj.id,
                    text=text,
                    content_hash=obj.content_hash,
                    published_at=obj.published_at,
                )
                self._initializer.bm25_index.add_document(bm25_doc)
                return True
            except Exception as e:
                last_error = e
                if attempt < BM25_MAX_RETRIES - 1:
                    delay = BM25_RETRY_BASE_DELAY * (2**attempt)
                    logger.debug(
                        "BM25 update attempt %d/%d failed for %s: %s. Retrying in %.1fs...",
                        attempt + 1,
                        BM25_MAX_RETRIES,
                        obj.id,
                        e,
                        delay,
                    )
                    time.sleep(delay)

        logger.warning(
            "BM25 update failed for %s after %d attempts: %s",
            obj.id,
            BM25_MAX_RETRIES,
            last_error,
        )
        return False

    # ------------------------------------------------------------------
    # Read Operations (delegate to RepositoryAccessService)
    # ------------------------------------------------------------------

    def get_knowledge_object(self, item_id: str) -> KnowledgeObject | None:
        """Get a single KnowledgeObject by ID.

        Args:
            item_id: Internal UUID of the knowledge object.

        Returns:
            KnowledgeObject if found, None otherwise.
        """
        return self._initializer.sqlite_store.get_by_id(item_id)

    def search_knowledge(self, query: KnowledgeQuery) -> KnowledgeListResponse:
        """Search knowledge using typed query.

        Args:
            query: KnowledgeQuery with filters and pagination.

        Returns:
            KnowledgeListResponse with matching items.
        """
        return self._access_service.search_knowledge(query)

    def get_statistics(self) -> RepositoryStatistics:
        """Get aggregate statistics for the repository.

        Returns:
            RepositoryStatistics with totals and breakdowns.
        """
        return self._access_service.get_statistics()

    # ------------------------------------------------------------------
    # Lifecycle Operations (delegate to RepositoryLifecycleService)
    # ------------------------------------------------------------------

    def get_lifecycle(self) -> RepositoryLifecycleService:
        """Return the lifecycle service for backup/restore operations."""
        return self._lifecycle_service
