"""Unit tests for KnowledgeUpdateService."""

from collections.abc import Generator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from app.core.utils import compute_text_hash
from app.models.knowledge_object import KnowledgeObject
from app.models.metadata import ExtractionResult
from app.services.knowledge.update_service import KnowledgeUpdateService
from app.storage.knowledge import SQLiteKnowledgeStore

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "test_update_service.db"


@pytest.fixture
def store(db_path: Path) -> Generator[SQLiteKnowledgeStore, Any, None]:
    s = SQLiteKnowledgeStore(db_path=db_path)
    yield s
    s.close()


@pytest.fixture
def service(store: SQLiteKnowledgeStore) -> KnowledgeUpdateService:
    return KnowledgeUpdateService(store)


def _make_ko(
    external_id: str = "ext_001",
    content: str = "Test content.",
    metadata: ExtractionResult | None = None,
) -> KnowledgeObject:
    if metadata is None:
        metadata = ExtractionResult(
            summary="Original summary",
            topics=["AI", "ML"],
            entities=["OpenAI"],
            relevance_score=0.8,
        )
    return KnowledgeObject(
        source_type="rss",
        source_name="test_source",
        external_id=external_id,
        source_url=f"https://example.com/{external_id}",
        content_hash=compute_text_hash(content),
        fetched_at=datetime(2025, 1, 2, 10, 0, 0, tzinfo=timezone.utc),
        published_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        title="Test Title",
        content_text=content,
        metadata=metadata,
    )


# =============================================================================
# update_metadata Tests
# =============================================================================


class TestUpdateMetadata:
    """Tests for KnowledgeUpdateService.update_metadata method."""

    def test_update_summary_only(
        self, store: SQLiteKnowledgeStore, service: KnowledgeUpdateService
    ) -> None:
        """Update only summary, keep other fields."""
        ko = _make_ko()
        store.save_objects([ko])

        result = service.update_metadata(ko.id, new_summary="New summary")
        assert result is True

        retrieved = store.get_by_id(ko.id)
        assert retrieved is not None
        assert retrieved.metadata.summary == "New summary"
        assert retrieved.metadata.topics == ["AI", "ML"]  # Unchanged

    def test_update_multiple_fields(
        self, store: SQLiteKnowledgeStore, service: KnowledgeUpdateService
    ) -> None:
        """Update multiple metadata fields."""
        ko = _make_ko()
        store.save_objects([ko])

        result = service.update_metadata(
            ko.id,
            new_summary="New summary",
            new_topics=["NLP", "LLM"],
            new_relevance_score=0.95,
        )
        assert result is True

        retrieved = store.get_by_id(ko.id)
        assert retrieved is not None
        assert retrieved.metadata.summary == "New summary"
        assert retrieved.metadata.topics == ["NLP", "LLM"]
        assert retrieved.metadata.relevance_score == 0.95

    def test_update_nonexistent(self, service: KnowledgeUpdateService) -> None:
        """Update non-existent ID returns False."""
        result = service.update_metadata("nonexistent", new_summary="Test")
        assert result is False


# =============================================================================
# merge_metadata Tests
# =============================================================================


class TestMergeMetadata:
    """Tests for KnowledgeUpdateService.merge_metadata method."""

    def test_merge_topics(
        self, store: SQLiteKnowledgeStore, service: KnowledgeUpdateService
    ) -> None:
        """Merge new topics into existing."""
        metadata = ExtractionResult(
            summary="Summary",
            topics=["AI", "ML"],
            entities=["OpenAI"],
            relevance_score=0.8,
        )
        ko = _make_ko(metadata=metadata)
        store.save_objects([ko])

        result = service.merge_metadata(ko.id, additional_topics=["NLP", "LLM"])
        assert result is True

        retrieved = store.get_by_id(ko.id)
        assert retrieved is not None
        # Topics should include both old and new (deduplicated)
        assert set(retrieved.metadata.topics) == {"AI", "ML", "NLP", "LLM"}

    def test_merge_entities(
        self, store: SQLiteKnowledgeStore, service: KnowledgeUpdateService
    ) -> None:
        """Merge new entities into existing."""
        metadata = ExtractionResult(
            summary="Summary",
            topics=["AI"],
            entities=["OpenAI"],
            relevance_score=0.8,
        )
        ko = _make_ko(metadata=metadata)
        store.save_objects([ko])

        result = service.merge_metadata(ko.id, additional_entities=["Google", "Meta"])
        assert result is True

        retrieved = store.get_by_id(ko.id)
        assert retrieved is not None
        assert set(retrieved.metadata.entities) == {"OpenAI", "Google", "Meta"}


# =============================================================================
# reprocess_content Tests
# =============================================================================


class TestReprocessContent:
    """Tests for KnowledgeUpdateService.reprocess_content method."""

    def test_reprocess_content_only(
        self, store: SQLiteKnowledgeStore, service: KnowledgeUpdateService
    ) -> None:
        """Reprocess content, keep title."""
        ko = _make_ko(content="Old content")
        store.save_objects([ko])

        result = service.reprocess_content(ko.id, "New content")
        assert result is True

        retrieved = store.get_by_id(ko.id)
        assert retrieved is not None
        assert retrieved.content_text == "New content"
        assert retrieved.title == "Test Title"  # Unchanged

    def test_reprocess_with_new_title(
        self, store: SQLiteKnowledgeStore, service: KnowledgeUpdateService
    ) -> None:
        """Reprocess content with new title."""
        ko = _make_ko(content="Old content")
        store.save_objects([ko])

        result = service.reprocess_content(ko.id, "New content", new_title="New Title")
        assert result is True

        retrieved = store.get_by_id(ko.id)
        assert retrieved is not None
        assert retrieved.content_text == "New content"
        assert retrieved.title == "New Title"
