"""Abstract interface for KnowledgeObject persistence.

Defines the contract that all storage backends must implement,
enabling the pipeline to remain agnostic of the underlying storage technology.
"""

from typing import Protocol

from app.models.knowledge_object import KnowledgeObject


class KnowledgeStore(Protocol):
    """Protocol defining the interface for KnowledgeObject storage.

    Implementations may use JSON files, PostgreSQL, Qdrant, or any other
    backend. The pipeline interacts only through this interface.

    Thread Safety:
        Implementations are responsible for their own concurrency handling.
    """

    def save_objects(self, objects: list[KnowledgeObject]) -> int:
        """Persist a batch of KnowledgeObjects with idempotent semantics.

        For each object:
        - If an existing record matches by (external_id, source_type)
          or content_hash, the record is updated.
        - Otherwise, a new record is created.

        Args:
            objects: List of validated KnowledgeObjects to persist.

        Returns:
            Number of newly created objects (not updates).
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

        Used to detect duplicate content across different sources.

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
