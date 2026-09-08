"""Vector Store Protocol and Data Models.

Defines the interface for vector database operations.
All vector stores must implement this protocol.
"""

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class VectorPoint:
    """A single vector point in the vector database.

    Attributes:
        id: Unique identifier (uses knowledge_id from KnowledgeObject).
        vector: Embedding vector.
        payload: Metadata payload for filtering (source_type, title, topics, etc.).
    """

    id: str
    vector: list[float]
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class UpsertResult:
    """Result of an upsert operation.

    Attributes:
        upserted: Number of points upserted.
        skipped: Number of points skipped (already exist with same content).
    """

    upserted: int
    skipped: int

    @property
    def total_processed(self) -> int:
        """Total number of points processed."""
        return self.upserted + self.skipped


class VectorStore(Protocol):
    """Protocol for vector database operations.

    Implementations must provide:
    - upsert_points: Insert or update vector points
    - delete_points: Delete vector points by ID
    - get_point: Retrieve a single point by ID
    - collection_exists: Check if a collection exists
    - create_collection: Create a new collection
    """

    def upsert_points(self, points: list[VectorPoint]) -> int:
        """Upsert vector points into the store.

        Args:
            points: List of VectorPoints to upsert.

        Returns:
            Number of points upserted.

        Raises:
            VectorStoreError: If upsert fails.
        """
        ...

    def delete_points(self, ids: list[str]) -> int:
        """Delete vector points by their IDs.

        Args:
            ids: List of point IDs to delete.

        Returns:
            Number of points deleted.

        Raises:
            VectorStoreError: If delete fails.
        """
        ...

    def get_point(self, point_id: str) -> VectorPoint | None:
        """Retrieve a single vector point by ID.

        Args:
            point_id: The point ID to retrieve.

        Returns:
            The VectorPoint if found, None otherwise.

        Raises:
            VectorStoreError: If retrieval fails.
        """
        ...

    def collection_exists(self, name: str) -> bool:
        """Check if a collection exists.

        Args:
            name: Collection name.

        Returns:
            True if collection exists, False otherwise.

        Raises:
            VectorStoreError: If check fails.
        """
        ...

    def create_collection(self, name: str, dimensions: int) -> None:
        """Create a new collection.

        Args:
            name: Collection name.
            dimensions: Vector dimensions.

        Raises:
            VectorStoreError: If creation fails.
        """
        ...
