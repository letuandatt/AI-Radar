"""Knowledge Update Service.

High-level update operations with validation and business logic.
Wraps SQLiteKnowledgeStore update methods.
"""

from app.core.logger import get_logger
from app.models.knowledge_object import KnowledgeObject
from app.models.metadata import ExtractionResult
from app.storage.knowledge.sqlite_store import SQLiteKnowledgeStore, UpdateResult

logger = get_logger(__name__)


class KnowledgeUpdateService:
    """High-level update operations for KnowledgeObjects.

    Provides business-level update methods with validation.

    Args:
        store: SQLiteKnowledgeStore instance.

    Example:
        service = KnowledgeUpdateService(store)
        service.update_metadata(obj_id, new_summary="Updated summary")
    """

    def __init__(self, store: SQLiteKnowledgeStore) -> None:
        self._store = store

    def update_metadata(
        self,
        obj_id: str,
        new_summary: str | None = None,
        new_topics: list[str] | None = None,
        new_entities: list[str] | None = None,
        new_relevance_score: float | None = None,
    ) -> bool:
        """Update metadata fields selectively.

        Only updates fields that are provided (not None).

        Args:
            obj_id: Internal ID of the KnowledgeObject.
            new_summary: New summary text.
            new_topics: New list of topics.
            new_entities: New list of entities.
            new_relevance_score: New relevance score.

        Returns:
            True if updated, False if not found.
        """
        # Fetch current object
        existing = self._store.get_by_id(obj_id)
        if existing is None:
            logger.warning("Cannot update metadata: ID %s not found", obj_id)
            return False

        # Build new metadata by merging
        current_metadata = existing.metadata

        new_metadata = ExtractionResult(
            summary=new_summary if new_summary is not None else current_metadata.summary,
            topics=new_topics if new_topics is not None else current_metadata.topics,
            entities=new_entities if new_entities is not None else current_metadata.entities,
            relevance_score=new_relevance_score
            if new_relevance_score is not None
            else current_metadata.relevance_score,
        )

        return self._store.update_metadata_by_id(obj_id, new_metadata)

    def merge_metadata(
        self,
        obj_id: str,
        additional_topics: list[str] | None = None,
        additional_entities: list[str] | None = None,
    ) -> bool:
        """Merge new topics/entities into existing metadata.

        Args:
            obj_id: Internal ID of the KnowledgeObject.
            additional_topics: Topics to add (deduplicated).
            additional_entities: Entities to add (deduplicated).

        Returns:
            True if updated, False if not found.
        """
        existing = self._store.get_by_id(obj_id)
        if existing is None:
            logger.warning("Cannot merge metadata: ID %s not found", obj_id)
            return False

        current_metadata = existing.metadata

        # Merge topics (deduplicate)
        merged_topics = list(set(current_metadata.topics))
        if additional_topics:
            merged_topics.extend(additional_topics)
            merged_topics = list(set(merged_topics))

        # Merge entities (deduplicate)
        merged_entities = list(set(current_metadata.entities))
        if additional_entities:
            merged_entities.extend(additional_entities)
            merged_entities = list(set(merged_entities))

        new_metadata = ExtractionResult(
            summary=current_metadata.summary,
            topics=merged_topics,
            entities=merged_entities,
            relevance_score=current_metadata.relevance_score,
        )

        return self._store.update_metadata_by_id(obj_id, new_metadata)

    def reprocess_content(
        self, obj_id: str, new_content: str, new_title: str | None = None
    ) -> bool:
        """Update content and optionally title.

        Note: This does NOT trigger LLM re-extraction. That would be a separate
        pipeline operation in Sprint 17 (Repository Management).

        Args:
            obj_id: Internal ID of the KnowledgeObject.
            new_content: New content text.
            new_title: New title (optional, keeps existing if None).

        Returns:
            True if updated, False if not found.
        """
        existing = self._store.get_by_id(obj_id)
        if existing is None:
            logger.warning("Cannot reprocess content: ID %s not found", obj_id)
            return False

        title = new_title if new_title is not None else existing.title
        return self._store.update_content_by_id(obj_id, title, new_content)

    def batch_update_objects(self, objects: list[KnowledgeObject]) -> UpdateResult:
        """Batch update multiple KnowledgeObjects.

        Idempotent: skips objects with non-existent IDs.

        Args:
            objects: List of KnowledgeObjects to update.

        Returns:
            UpdateResult with updated and skipped counts.
        """
        return self._store.batch_update(objects)
