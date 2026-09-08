"""Vector Sync Service.

Orchestrates consistency between SQLite (KnowledgeObjects) and Qdrant (vectors).
Handles single-object sync, orphan cleanup, and full reindexing.
"""

from app.core.logger import get_logger
from app.models.knowledge_object import KnowledgeObject
from app.services.embedding.context_builder import ContextBuilder
from app.services.embedding.provider import EmbeddingProvider
from app.storage.knowledge.sqlite_store import SQLiteKnowledgeStore
from app.storage.vector.base import VectorPoint
from app.storage.vector.qdrant_store import QdrantVectorStore

logger = get_logger(__name__)


class VectorSyncService:
    """Orchestrates vector sync operations between SQLite and Qdrant.

    Args:
        vector_store: QdrantVectorStore instance.
        context_builder: ContextBuilder for CCH generation.
    """

    def __init__(
        self,
        vector_store: QdrantVectorStore,
        context_builder: ContextBuilder | None = None,
    ) -> None:
        self._vector_store = vector_store
        self._context_builder = context_builder or ContextBuilder()

    # ------------------------------------------------------------------
    # Single Object Sync
    # ------------------------------------------------------------------

    def sync_knowledge_object(
        self,
        obj: KnowledgeObject,
        embedding_provider: EmbeddingProvider,
    ) -> bool:
        """Sync a single KnowledgeObject to the vector store.

        Steps:
        1. Build CCH (Contextual Chunk Header)
        2. Generate embedding vector
        3. Build payload from KnowledgeObject
        4. Upsert to Qdrant with ID = obj.id

        Args:
            obj: KnowledgeObject to sync.
            embedding_provider: Provider for embedding generation.

        Returns:
            True if sync succeeded.

        Raises:
            Exception: If embedding or upsert fails.
        """
        # Step 1: Build CCH
        cch_text = self._context_builder.build_for_embedding(obj)

        # Step 2: Generate embedding
        logger.debug(
            "Generating embedding for KnowledgeObject %s",
            obj.id,
        )
        vector = embedding_provider.embed_text(cch_text)

        # Step 3: Build payload
        payload = self._vector_store.build_payload(obj)

        # Step 4: Build VectorPoint and upsert
        point = VectorPoint(
            id=obj.id,
            vector=vector,
            payload=payload,
        )

        count = self._vector_store.upsert_points([point])

        logger.info(
            "Synced KnowledgeObject %s to vector store (upserted=%d)",
            obj.id,
            count,
        )
        return count > 0  # type: ignore[no-any-return]

    # ------------------------------------------------------------------
    # Orphan Cleanup
    # ------------------------------------------------------------------

    def delete_orphaned_vectors(self, valid_ids: set[str]) -> int:
        """Delete vectors that don't have corresponding KnowledgeObjects.

        Scans all points in Qdrant, compares with valid_ids set,
        and deletes points whose IDs are not in valid_ids.

        This is the implementation behind
        KnowledgeDeleteService.cleanup_orphaned_vectors().

        Args:
            valid_ids: Set of KnowledgeObject IDs that exist in SQLite.

        Returns:
            Number of orphaned vectors deleted.
        """
        logger.info(
            "Scanning for orphaned vectors (valid_ids count: %d)",
            len(valid_ids),
        )

        # Get all point IDs from Qdrant
        all_point_ids = self._vector_store.get_all_point_ids()

        # Find orphaned IDs (in Qdrant but not in valid_ids)
        orphaned_ids = [pid for pid in all_point_ids if pid not in valid_ids]

        if not orphaned_ids:
            logger.info("No orphaned vectors found")
            return 0

        # Delete orphaned points
        deleted_count = self._vector_store.delete_by_knowledge_ids(orphaned_ids)

        logger.info(
            "Deleted %d orphaned vectors (total scanned: %d, valid: %d)",
            deleted_count,
            len(all_point_ids),
            len(valid_ids),
        )

        return deleted_count

    # ------------------------------------------------------------------
    # Full Reindex
    # ------------------------------------------------------------------

    def full_reindex(
        self,
        knowledge_store: SQLiteKnowledgeStore,
        embedding_provider: EmbeddingProvider,
        batch_size: int = 100,
    ) -> int:
        """Full reindex: rebuild all vectors from SQLite KnowledgeObjects.

        Use this when:
        - Changing embedding model
        - Migrating to new Qdrant collection
        - Recovering from data inconsistency

        Steps:
        1. Clear existing Qdrant collection
        2. Load all KnowledgeObjects from SQLite
        3. Batch embed and upsert to Qdrant

        Args:
            knowledge_store: SQLiteKnowledgeStore to load from.
            embedding_provider: Provider for embedding generation.
            batch_size: Number of objects to embed per batch (default: 100).

        Returns:
            Total number of objects reindexed.
        """
        logger.info("Starting full reindex operation")

        # Step 1: Clear collection
        cleared = self._vector_store.reindex_collection()
        logger.info("Cleared %d existing vectors", cleared)

        # Step 2: Load all KnowledgeObjects
        all_objects = knowledge_store.get_all()
        total = len(all_objects)
        logger.info("Loaded %d KnowledgeObjects from SQLite", total)

        if total == 0:
            logger.info("No objects to reindex")
            return 0

        # Step 3: Batch embed and upsert
        reindexed = 0
        for i in range(0, total, batch_size):
            batch = all_objects[i : i + batch_size]
            batch_count = self._reindex_batch(batch, embedding_provider)
            reindexed += batch_count
            logger.info(
                "Reindex progress: %d/%d objects (%.1f%%)",
                reindexed,
                total,
                (reindexed / total) * 100,
            )

        logger.info("Full reindex completed: %d objects", reindexed)
        return reindexed

    def _reindex_batch(
        self,
        objects: list[KnowledgeObject],
        embedding_provider: EmbeddingProvider,
    ) -> int:
        """Reindex a single batch of KnowledgeObjects.

        Args:
            objects: Batch of KnowledgeObjects.
            embedding_provider: Provider for embedding generation.

        Returns:
            Number of objects successfully reindexed.
        """
        # Build CCH texts for all objects
        cch_texts = self._context_builder.build_batch_for_embedding(objects)

        # Batch embed
        vectors = embedding_provider.embed_batch(cch_texts)

        # Build VectorPoints
        points = []
        for obj, vector in zip(objects, vectors):
            payload = self._vector_store.build_payload(obj)
            point = VectorPoint(
                id=obj.id,
                vector=vector,
                payload=payload,
            )
            points.append(point)

        # Upsert batch
        count = self._vector_store.upsert_points(points)
        return count  # type: ignore[no-any-return]
