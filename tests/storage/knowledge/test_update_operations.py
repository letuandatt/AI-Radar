"""Unit tests for SQLiteKnowledgeStore update operations."""

from collections.abc import Generator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from app.core.utils import compute_text_hash
from app.models.knowledge_object import KnowledgeObject
from app.models.metadata import ExtractionResult
from app.storage.knowledge import SQLiteKnowledgeStore, UpdateResult

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "test_update.db"


@pytest.fixture
def store(db_path: Path) -> Generator[SQLiteKnowledgeStore, Any, None]:
    s = SQLiteKnowledgeStore(db_path=db_path)
    yield s
    s.close()


@pytest.fixture
def sample_metadata() -> ExtractionResult:
    return ExtractionResult(
        summary="Original summary.",
        topics=["AI", "ML"],
        entities=["OpenAI"],
        relevance_score=0.8,
    )


def _make_ko(
    external_id: str = "ext_001",
    content: str = "Test content.",
    title: str = "Test Title",
    metadata: ExtractionResult | None = None,
) -> KnowledgeObject:
    if metadata is None:
        metadata = ExtractionResult(
            summary="Summary",
            topics=["AI"],
            entities=["Entity"],
            relevance_score=0.9,
        )
    return KnowledgeObject(
        source_type="rss",
        source_name="test_source",
        external_id=external_id,
        source_url=f"https://example.com/{external_id}",
        content_hash=compute_text_hash(content),
        fetched_at=datetime(2025, 1, 2, 10, 0, 0, tzinfo=timezone.utc),
        published_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        title=title,
        content_text=content,
        metadata=metadata,
    )


# =============================================================================
# update_by_id Tests
# =============================================================================


class TestUpdateById:
    """Tests for partial update_by_id method."""

    def test_update_title_only(self, store: SQLiteKnowledgeStore) -> None:
        """Update title, verify content_text unchanged."""
        ko = _make_ko(title="Old Title", content="Keep this content")
        store.save_objects([ko])

        result = store.update_by_id(ko.id, {"title": "New Title"})
        assert result is True

        retrieved = store.get_by_id(ko.id)
        assert retrieved is not None
        assert retrieved.title == "New Title"
        assert retrieved.content_text == "Keep this content"

    def test_update_nonexistent_id(self, store: SQLiteKnowledgeStore) -> None:
        """Update non-existent ID returns False."""
        result = store.update_by_id("nonexistent_id", {"title": "New"})
        assert result is False

    def test_update_forbidden_field(self, store: SQLiteKnowledgeStore) -> None:
        """Updating forbidden field raises ValueError."""
        ko = _make_ko()
        store.save_objects([ko])

        with pytest.raises(ValueError, match="forbidden fields"):
            store.update_by_id(ko.id, {"source_type": "github"})

    def test_update_metadata(self, store: SQLiteKnowledgeStore) -> None:
        """Update metadata field."""
        ko = _make_ko()
        store.save_objects([ko])

        new_metadata = ExtractionResult(
            summary="Updated summary",
            topics=["NLP", "LLM"],
            entities=["Google"],
            relevance_score=0.95,
        )

        result = store.update_by_id(ko.id, {"metadata": new_metadata})
        assert result is True

        retrieved = store.get_by_id(ko.id)
        assert retrieved is not None
        assert retrieved.metadata.summary == "Updated summary"
        assert retrieved.metadata.topics == ["NLP", "LLM"]

    def test_update_updates_timestamp(self, store: SQLiteKnowledgeStore) -> None:
        """Update operation updates updated_at timestamp."""
        ko = _make_ko()
        store.save_objects([ko])

        original = store.get_by_id(ko.id)
        assert original is not None
        original_updated_at = original.updated_at

        # Small delay to ensure timestamp differs
        import time

        time.sleep(0.01)

        store.update_by_id(ko.id, {"title": "Updated"})

        updated = store.get_by_id(ko.id)
        assert updated is not None
        assert updated.updated_at > original_updated_at


# =============================================================================
# update_metadata_by_id Tests
# =============================================================================


class TestUpdateMetadataById:
    """Tests for update_metadata_by_id method."""

    def test_update_metadata_only(self, store: SQLiteKnowledgeStore) -> None:
        """Update metadata, verify content unchanged."""
        ko = _make_ko(content="Keep this")
        store.save_objects([ko])

        new_metadata = ExtractionResult(
            summary="New summary",
            topics=["New Topic"],
            entities=["New Entity"],
            relevance_score=0.7,
        )

        result = store.update_metadata_by_id(ko.id, new_metadata)
        assert result is True

        retrieved = store.get_by_id(ko.id)
        assert retrieved is not None
        assert retrieved.metadata.summary == "New summary"
        assert retrieved.content_text == "Keep this"


# =============================================================================
# update_content_by_id Tests
# =============================================================================


class TestUpdateContentById:
    """Tests for update_content_by_id method."""

    def test_update_content_recalculates_hash(self, store: SQLiteKnowledgeStore) -> None:
        """Update content, verify content_hash recalculated."""
        ko = _make_ko(content="Old content")
        store.save_objects([ko])

        old_hash = ko.content_hash
        new_content = "New content here"
        expected_hash = compute_text_hash(new_content)

        result = store.update_content_by_id(ko.id, "New Title", new_content)
        assert result is True

        retrieved = store.get_by_id(ko.id)
        assert retrieved is not None
        assert retrieved.title == "New Title"
        assert retrieved.content_text == new_content
        assert retrieved.content_hash == expected_hash
        assert retrieved.content_hash != old_hash


# =============================================================================
# touch_by_id Tests
# =============================================================================


class TestTouchById:
    """Tests for touch_by_id method."""

    def test_touch_updates_timestamp_only(self, store: SQLiteKnowledgeStore) -> None:
        """Touch updates only updated_at, not other fields."""
        ko = _make_ko(title="Original Title", content="Original Content")
        store.save_objects([ko])

        original = store.get_by_id(ko.id)
        assert original is not None

        import time

        time.sleep(0.01)

        result = store.touch_by_id(ko.id)
        assert result is True

        touched = store.get_by_id(ko.id)
        assert touched is not None
        assert touched.title == "Original Title"
        assert touched.content_text == "Original Content"
        assert touched.updated_at > original.updated_at

    def test_touch_nonexistent(self, store: SQLiteKnowledgeStore) -> None:
        """Touch non-existent ID returns False."""
        result = store.touch_by_id("nonexistent")
        assert result is False


# =============================================================================
# batch_update Tests
# =============================================================================


class TestBatchUpdate:
    """Tests for batch_update method."""

    def test_batch_update_all_exist(self, store: SQLiteKnowledgeStore) -> None:
        """Batch update where all IDs exist."""
        ko1 = _make_ko(external_id="1", title="Title 1")
        ko2 = _make_ko(external_id="2", title="Title 2")
        store.save_objects([ko1, ko2])

        # Modify titles
        ko1_modified = ko1.model_copy(update={"title": "Updated 1"})
        ko2_modified = ko2.model_copy(update={"title": "Updated 2"})

        result = store.batch_update([ko1_modified, ko2_modified])
        assert result.updated == 2
        assert result.skipped == 0

        # Verify
        r1 = store.get_by_id(ko1.id)
        r2 = store.get_by_id(ko2.id)
        assert r1 is not None and r1.title == "Updated 1"
        assert r2 is not None and r2.title == "Updated 2"

    def test_batch_update_some_missing(self, store: SQLiteKnowledgeStore) -> None:
        """Batch update with some non-existent IDs (idempotent)."""
        ko1 = _make_ko(external_id="1")
        store.save_objects([ko1])

        # Create a fake KO with non-existent ID
        fake_ko = _make_ko(external_id="fake")
        fake_ko.id = "nonexistent_id"

        ko1_modified = ko1.model_copy(update={"title": "Updated"})

        result = store.batch_update([ko1_modified, fake_ko])
        assert result.updated == 1
        assert result.skipped == 1

    def test_batch_update_empty(self, store: SQLiteKnowledgeStore) -> None:
        """Empty batch returns zero counts."""
        result = store.batch_update([])
        assert result.updated == 0
        assert result.skipped == 0

    def test_update_result_dataclass(self) -> None:
        """UpdateResult has correct properties."""
        result = UpdateResult(updated=3, skipped=1)
        assert result.total_processed == 4
