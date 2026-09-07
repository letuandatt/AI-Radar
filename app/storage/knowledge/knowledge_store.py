"""Abstract interface for KnowledgeObject persistence.

Defines the contract that all storage backends must implement,
enabling the pipeline to remain agnostic of the underlying storage technology.
"""

from dataclasses import dataclass
from typing import Protocol

from app.models.knowledge_object import KnowledgeObject


@dataclass(frozen=True)
class SaveResult:
    """Result of a save_objects() operation.

    Attributes:
        created: Number of newly inserted objects.
        updated: Number of existing objects updated (content changed).
        skipped: Number of objects skipped (content unchanged, idempotent).
    """

    created: int
    updated: int
    skipped: int

    @property
    def total_processed(self) -> int:
        """Total number of objects processed."""
        return self.created + self.updated + self.skipped


class KnowledgeStore(Protocol):
    """Protocol defining the interface for KnowledgeObject storage.

    Implementations may use JSON files, SQLite, PostgreSQL, or any other
    backend. The pipeline interacts only through this interface.

    Thread Safety:
        Implementations are responsible for their own concurrency handling.
    """

    def save_objects(self, objects: list[KnowledgeObject]) -> SaveResult:
        """Persist a batch of KnowledgeObjects with idempotent semantics.

        For each object:
        - If not found by identity → INSERT (created)
        - If found and content_hash differs → UPDATE (updated)
        - If found and content_hash same → SKIP (skipped)

        Args:
            objects: List of validated KnowledgeObjects to persist.

        Returns:
            SaveResult with created, updated, and skipped counts.
        """
        ...

    def get_by_external_id(self, external_id: str, source_type: str) -> KnowledgeObject | None:
        """Retrieve a KnowledgeObject by its external identity.

        Args:
            external_id: The external identifier from the source.
            source_type: The source type to disambiguate.

        Returns:
            The matching KnowledgeObject, or None if not found.
        """
        ...

    def get_by_content_hash(self, content_hash: str) -> KnowledgeObject | None:
        """Retrieve a KnowledgeObject by its content hash.

        Args:
            content_hash: SHA-256 hash of the content text.

        Returns:
            The matching KnowledgeObject, or None if not found.
        """
        ...

    def get_all(self) -> list[KnowledgeObject]:
        """Retrieve all stored KnowledgeObjects.

        Returns:
            List of all KnowledgeObjects in the store.
        """
        ...

    def count(self) -> int:
        """Return the total number of stored KnowledgeObjects.

        Returns:
            Total object count.
        """
        ...
