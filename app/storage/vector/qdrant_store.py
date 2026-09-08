"""Qdrant Vector Store Implementation.

Implements the VectorStore protocol using Qdrant as the backend.
Supports idempotent upsert, payload filtering, and reliability patterns.
"""

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.http import models as qdrant_models
from qdrant_client.http.exceptions import UnexpectedResponse

from app.core.logger import get_logger
from app.storage.knowledge.base import (
    CircuitBreaker,
    retry_on_transient_error,
)
from app.storage.vector.base import VectorPoint
from app.storage.vector.config import (
    QDRANT_BATCH_SIZE,
    QDRANT_CIRCUIT_FAILURE_THRESHOLD,
    QDRANT_CIRCUIT_RECOVERY_TIMEOUT,
    QDRANT_COLLECTION_NAME,
    QDRANT_MAX_RETRIES,
    QDRANT_RETRY_BASE_DELAY,
    QDRANT_TIMEOUT,
    QDRANT_URL,
)

logger = get_logger(__name__)


class VectorStoreError(Exception):
    """Raised when vector store operation fails."""

    pass


class QdrantVectorStore:
    """Qdrant-based vector store implementation.

    Provides idempotent upsert, payload filtering, and reliability patterns
    (retry, timeout, circuit breaker).

    Args:
        url: Qdrant server URL (default: http://localhost:6333).
        collection_name: Collection name (default: knowledge_objects).
        dimensions: Vector dimensions (must match embedding provider).
        timeout: Request timeout in seconds (default: 30).
        max_retries: Max retries for transient errors (default: 3).
        circuit_breaker: Optional CircuitBreaker instance.
    """

    def __init__(
        self,
        url: str = QDRANT_URL,
        collection_name: str = QDRANT_COLLECTION_NAME,
        dimensions: int | None = None,
        timeout: int = QDRANT_TIMEOUT,
        max_retries: int = QDRANT_MAX_RETRIES,
        circuit_breaker: CircuitBreaker | None = None,
    ) -> None:
        self._url = url
        self._collection_name = collection_name
        self._dimensions = dimensions
        self._timeout = timeout
        self._max_retries = max_retries
        self._circuit_breaker = circuit_breaker or CircuitBreaker(
            failure_threshold=QDRANT_CIRCUIT_FAILURE_THRESHOLD,
            recovery_timeout=QDRANT_CIRCUIT_RECOVERY_TIMEOUT,
        )
        self._client = QdrantClient(url=url, timeout=timeout)

    # ------------------------------------------------------------------
    # Circuit Breaker Guard
    # ------------------------------------------------------------------

    def _check_circuit(self) -> None:
        """Raise if circuit breaker is open."""
        if not self._circuit_breaker.allow_request():
            raise VectorStoreError(
                "QdrantVectorStore circuit breaker is open. Operations are temporarily suspended."
            )

    # ------------------------------------------------------------------
    # Collection Management
    # ------------------------------------------------------------------

    def collection_exists(self, name: str | None = None) -> bool:
        """Check if a collection exists.

        Args:
            name: Collection name (defaults to configured collection).

        Returns:
            True if collection exists, False otherwise.
        """
        self._check_circuit()

        collection = name or self._collection_name

        try:
            collections = self._client.get_collections().collections
            exists = any(c.name == collection for c in collections)
            self._circuit_breaker.record_success()
            return exists
        except Exception as e:
            self._circuit_breaker.record_failure()
            logger.error("Failed to check collection existence: %s", e)
            raise VectorStoreError(f"Failed to check collection: {e}") from e

    @retry_on_transient_error(
        max_retries=QDRANT_MAX_RETRIES,
        base_delay=QDRANT_RETRY_BASE_DELAY,
        retryable_exceptions=(Exception,),
    )
    def create_collection(self, name: str | None = None, dimensions: int | None = None) -> None:
        """Create a new collection if it doesn't exist.

        Args:
            name: Collection name (defaults to configured collection).
            dimensions: Vector dimensions (defaults to configured dimensions).

        Raises:
            VectorStoreError: If dimensions not specified and not configured.
        """
        self._check_circuit()

        collection = name or self._collection_name
        dims = dimensions or self._dimensions

        if dims is None:
            raise VectorStoreError(
                "Vector dimensions not specified. "
                "Provide dimensions parameter or configure in constructor."
            )

        try:
            self._client.create_collection(
                collection_name=collection,
                vectors_config=qdrant_models.VectorParams(
                    size=dims,
                    distance=qdrant_models.Distance.COSINE,
                ),
            )
            self._circuit_breaker.record_success()
            logger.info(
                "Created Qdrant collection '%s' with %d dimensions",
                collection,
                dims,
            )
        except UnexpectedResponse as e:
            if e.status_code == 409:
                # Collection already exists — not an error
                self._circuit_breaker.record_success()
                logger.info("Collection '%s' already exists", collection)
            else:
                self._circuit_breaker.record_failure()
                raise VectorStoreError(f"Failed to create collection: {e}") from e
        except Exception as e:
            self._circuit_breaker.record_failure()
            logger.error("Failed to create collection: %s", e)
            raise VectorStoreError(f"Failed to create collection: {e}") from e

    def ensure_collection(self, dimensions: int | None = None) -> None:
        """Ensure collection exists, create if not.

        Args:
            dimensions: Vector dimensions (uses configured if not provided).
        """
        if not self.collection_exists():
            self.create_collection(dimensions=dimensions)

    # ------------------------------------------------------------------
    # Point Operations
    # ------------------------------------------------------------------

    @retry_on_transient_error(
        max_retries=QDRANT_MAX_RETRIES,
        base_delay=QDRANT_RETRY_BASE_DELAY,
        retryable_exceptions=(Exception,),
    )
    def upsert_points(self, points: list[VectorPoint]) -> int:
        """Upsert vector points into the store.

        Qdrant native upsert: overwrites if ID exists, inserts if not.

        Args:
            points: List of VectorPoints to upsert.

        Returns:
            Number of points upserted.
        """
        self._check_circuit()

        if not points:
            return 0

        try:
            # Convert VectorPoint to Qdrant PointStruct
            qdrant_points = [
                qdrant_models.PointStruct(
                    id=point.id,
                    vector=point.vector,
                    payload=point.payload,
                )
                for point in points
            ]

            # Batch upsert
            for i in range(0, len(qdrant_points), QDRANT_BATCH_SIZE):
                batch = qdrant_points[i : i + QDRANT_BATCH_SIZE]
                self._client.upsert(
                    collection_name=self._collection_name,
                    points=batch,
                )

            self._circuit_breaker.record_success()
            logger.info("Upserted %d points into Qdrant", len(points))
            return len(points)

        except Exception as e:
            self._circuit_breaker.record_failure()
            logger.error("Failed to upsert points: %s", e)
            raise VectorStoreError(f"Failed to upsert points: {e}") from e

    @retry_on_transient_error(
        max_retries=QDRANT_MAX_RETRIES,
        base_delay=QDRANT_RETRY_BASE_DELAY,
        retryable_exceptions=(Exception,),
    )
    def delete_points(self, ids: Sequence[str]) -> int:
        """Delete vector points by their IDs.

        Args:
            ids: List of point IDs to delete.

        Returns:
            Number of points deleted.
        """
        self._check_circuit()

        if not ids:
            return 0

        try:
            self._client.delete(
                collection_name=self._collection_name,
                points_selector=qdrant_models.PointIdsList(points=list(ids)),
            )
            self._circuit_breaker.record_success()
            logger.info("Deleted %d points from Qdrant", len(ids))
            return len(ids)

        except Exception as e:
            self._circuit_breaker.record_failure()
            logger.error("Failed to delete points: %s", e)
            raise VectorStoreError(f"Failed to delete points: {e}") from e

    def get_point(self, point_id: str) -> VectorPoint | None:
        """Retrieve a single vector point by ID.

        Args:
            point_id: The point ID to retrieve.

        Returns:
            The VectorPoint if found, None otherwise.
        """
        self._check_circuit()

        try:
            result = self._client.retrieve(
                collection_name=self._collection_name,
                ids=[point_id],
                with_payload=True,
                with_vectors=True,
            )

            if not result:
                return None

            point = result[0]

            # Qdrant may return named vectors or single vector
            # We assume single vector mode (not named vectors)
            vector = point.vector
            if not isinstance(vector, list):
                raise VectorStoreError(
                    f"Unexpected vector type for point {point_id}: {type(vector)}. "
                    f"Expected list[float] (single vector mode)."
                )

            # Type assertion: cast to list[float]
            from typing import cast

            vector_typed = cast("list[float]", vector)

            self._circuit_breaker.record_success()
            return VectorPoint(
                id=str(point.id),
                vector=vector_typed,
                payload=point.payload or {},
            )

        except Exception as e:
            self._circuit_breaker.record_failure()
            logger.error("Failed to get point %s: %s", point_id, e)
            raise VectorStoreError(f"Failed to get point: {e}") from e

    def get_all_point_ids(self) -> list[str]:
        """Retrieve all point IDs in the collection.

        Returns:
            List of all point IDs.
        """
        self._check_circuit()

        try:
            # Scroll through all points to get IDs
            all_ids = []
            offset = None

            while True:
                result, offset = self._client.scroll(
                    collection_name=self._collection_name,
                    limit=1000,
                    offset=offset,
                    with_payload=False,
                    with_vectors=False,
                )

                all_ids.extend([str(point.id) for point in result])

                if offset is None:
                    break

            self._circuit_breaker.record_success()
            return all_ids

        except Exception as e:
            self._circuit_breaker.record_failure()
            logger.error("Failed to get all point IDs: %s", e)
            raise VectorStoreError(f"Failed to get all point IDs: {e}") from e

    def count(self) -> int:
        """Return the total number of points in the collection.

        Returns:
            Total point count.
        """
        self._check_circuit()

        try:
            info = self._client.get_collection(self._collection_name)
            self._circuit_breaker.record_success()

            # points_count may be None if collection metadata not available
            points_count = info.points_count
            if points_count is None:
                logger.warning(
                    "Collection %s points_count is None, returning 0",
                    self._collection_name,
                )
                return 0

            return points_count

        except Exception as e:
            self._circuit_breaker.record_failure()
            logger.error("Failed to count points: %s", e)
            raise VectorStoreError(f"Failed to count points: {e}") from e

    # ------------------------------------------------------------------
    # Update Operations
    # ------------------------------------------------------------------

    def update_vector(
        self,
        point_id: str,
        new_vector: list[float],
        new_payload: dict[str, Any] | None = None,
    ) -> bool:
        """Update vector and payload for a single point.

        Qdrant upsert overwrites existing point, so this effectively updates.
        If point does not exist, a new one will be created.

        Args:
            point_id: The point ID to update.
            new_vector: New embedding vector.
            new_payload: New payload (metadata). If None, keeps existing payload.

        Returns:
            True if update succeeded.

        Raises:
            VectorStoreError: If update fails.
        """
        self._check_circuit()

        try:
            # If new_payload is None, fetch existing payload first
            if new_payload is None:
                existing = self.get_point(point_id)
                if existing is None:
                    logger.warning(
                        "update_vector: Point %s not found, cannot update",
                        point_id,
                    )
                    return False
                new_payload = existing.payload

            point = qdrant_models.PointStruct(
                id=point_id,
                vector=new_vector,
                payload=new_payload,
            )

            self._client.upsert(
                collection_name=self._collection_name,
                points=[point],
            )

            self._circuit_breaker.record_success()
            logger.info("Updated vector for point %s", point_id)
            return True

        except Exception as e:
            self._circuit_breaker.record_failure()
            logger.error("Failed to update vector for point %s: %s", point_id, e)
            raise VectorStoreError(f"Failed to update vector: {e}") from e

    def delete_by_knowledge_ids(self, ids: Sequence[str]) -> int:
        """Delete multiple points by their knowledge IDs.

        This is a convenience wrapper around delete_points().

        Args:
            ids: List of knowledge IDs (used as point IDs) to delete.

        Returns:
            Number of points deleted.
        """
        return self.delete_points(ids)  # type: ignore[no-any-return]

    def reindex_collection(self) -> int:
        """Delete all points from the collection (full clear).

        Does NOT recreate the collection - just removes all data.
        Use this before a full reindex operation.

        Returns:
            Number of points deleted (before clearing).
        """
        self._check_circuit()

        try:
            # Get count before deletion
            count_before = self.count()

            # Delete all points using filter match all
            self._client.delete(
                collection_name=self._collection_name,
                points_selector=qdrant_models.FilterSelector(
                    filter=qdrant_models.Filter(
                        must=[],
                    )
                ),
            )

            self._circuit_breaker.record_success()
            logger.info(
                "Reindex: cleared %d points from collection %s",
                count_before,
                self._collection_name,
            )
            return count_before

        except Exception as e:
            self._circuit_breaker.record_failure()
            logger.error("Failed to reindex collection: %s", e)
            raise VectorStoreError(f"Failed to reindex collection: {e}") from e

    def build_payload(self, ko: Any) -> dict[str, Any]:
        """Build Qdrant payload from a KnowledgeObject.

        Args:
            ko: KnowledgeObject instance.

        Returns:
            Payload dict with all required fields.
        """
        return {
            "source_type": ko.source_type,
            "source_name": ko.source_name,
            "external_id": ko.external_id,
            "content_hash": ko.content_hash,
            "title": ko.title,
            "source_url": ko.source_url,
            "published_at": self._to_iso(ko.published_at),
            "topics": ko.metadata.topics,
            "entities": ko.metadata.entities,
        }

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Close the Qdrant client connection."""
        self._client.close()
        logger.info("Qdrant client closed")

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _to_iso(value: datetime | None) -> str | None:
        """Convert datetime to ISO string or None."""
        if value is None:
            return None
        return value.isoformat()
