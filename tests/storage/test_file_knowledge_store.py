"""Unit tests for FileKnowledgeStore with idempotent semantics."""

from datetime import datetime
from pathlib import Path

import pytest

from app.core.utils import compute_text_hash
from app.models.knowledge_object import KnowledgeObject
from app.models.metadata import ExtractionResult
from app.storage.file_knowledge_store import FileKnowledgeStore


@pytest.fixture
def storage_path(tmp_path: Path) -> Path:
    """Provide a temporary file path for testing."""
    return tmp_path / "knowledge_store.json"


@pytest.fixture
def store(storage_path: Path) -> FileKnowledgeStore:
    """Provide a FileKnowledgeStore instance."""
    return FileKnowledgeStore(file_path=storage_path)


@pytest.fixture
def sample_metadata() -> ExtractionResult:
    """Provide a valid ExtractionResult."""
    return ExtractionResult(
        summary="A concise summary.",
        topics=["AI", "Machine Learning"],
        entities=["OpenAI"],
        relevance_score=0.9,
    )


def _make_knowledge_object(
    external_id: str = "ext_001",
    source_type: str = "rss",
    source_name: str = "test_source",
    content: str = "Test content for knowledge object.",
    title: str = "Test Title",
    metadata: ExtractionResult | None = None,
) -> KnowledgeObject:
    """Helper to create a KnowledgeObject with sensible defaults."""
    if metadata is None:
        metadata = ExtractionResult(
            summary="A concise summary.",
            topics=["AI"],
            entities=["OpenAI"],
            relevance_score=0.9,
        )
    return KnowledgeObject(
        source_type=source_type,
        source_name=source_name,
        external_id=external_id,
        source_url=f"https://example.com/{external_id}",
        content_hash=compute_text_hash(content),
        fetched_at=datetime(2025, 1, 2, 10, 0, 0),
        published_at=datetime(2025, 1, 1, 12, 0, 0),
        title=title,
        content_text=content,
        metadata=metadata,
    )


# ==============================================================================
# Basic CRUD Tests
# ==============================================================================


class TestBasicOperations:
    """Tests for basic store operations."""

    def test_empty_store_count(self, store: FileKnowledgeStore) -> None:
        assert store.count() == 0
        assert store.get_all() == []

    def test_save_and_retrieve(self, store: FileKnowledgeStore) -> None:
        obj = _make_knowledge_object()
        created = store.save_objects([obj])

        assert created == 1
        assert store.count() == 1

        retrieved = store.get_by_external_id("ext_001", "rss")
        assert retrieved is not None
        assert retrieved.title == "Test Title"

    def test_get_by_content_hash(self, store: FileKnowledgeStore) -> None:
        obj = _make_knowledge_object(content="Unique content here")
        store.save_objects([obj])

        found = store.get_by_content_hash(compute_text_hash("Unique content here"))
        assert found is not None
        assert found.external_id == "ext_001"

    def test_get_by_content_hash_not_found(self, store: FileKnowledgeStore) -> None:
        result = store.get_by_content_hash("nonexistent_hash")
        assert result is None

    def test_get_by_external_id_not_found(self, store: FileKnowledgeStore) -> None:
        result = store.get_by_external_id("nonexistent", "rss")
        assert result is None


# ==============================================================================
# Idempotency Tests
# ==============================================================================


class TestIdempotency:
    """Tests for idempotent save behavior (create vs update)."""

    def test_first_save_creates_all(self, store: FileKnowledgeStore) -> None:
        """First call: all objects are new → all created."""
        obj_a = _make_knowledge_object(external_id="a", content="Content A")
        obj_b = _make_knowledge_object(external_id="b", content="Content B")
        obj_c = _make_knowledge_object(external_id="c", content="Content C")

        created = store.save_objects([obj_a, obj_b, obj_c])

        assert created == 3
        assert store.count() == 3

    def test_second_save_same_objects_creates_none(self, store: FileKnowledgeStore) -> None:
        """Second call with same objects: all are updates → 0 created."""
        obj_a = _make_knowledge_object(external_id="a", content="Content A")
        obj_b = _make_knowledge_object(external_id="b", content="Content B")
        obj_c = _make_knowledge_object(external_id="c", content="Content C")

        store.save_objects([obj_a, obj_b, obj_c])
        created = store.save_objects([obj_a, obj_b, obj_c])

        assert created == 0
        assert store.count() == 3

    def test_third_save_mixed_creates_only_new(self, store: FileKnowledgeStore) -> None:
        """Third call: 1 new + 2 existing → 1 created, 2 updated."""
        obj_a = _make_knowledge_object(external_id="a", content="Content A")
        obj_b = _make_knowledge_object(external_id="b", content="Content B")

        store.save_objects([obj_a, obj_b])

        # Modify A's title, keep B same, add new D
        obj_a_modified = _make_knowledge_object(
            external_id="a", content="Content A", title="Updated Title A"
        )
        obj_d = _make_knowledge_object(external_id="d", content="Content D")

        created = store.save_objects([obj_a_modified, obj_b, obj_d])

        assert created == 1  # Only D is new
        assert store.count() == 3  # A, B, D (A was updated, not duplicated)

        # Verify A was actually updated
        retrieved_a = store.get_by_external_id("a", "rss")
        assert retrieved_a is not None
        assert retrieved_a.title == "Updated Title A"

    def test_duplicate_content_hash_detected(self, store: FileKnowledgeStore) -> None:
        """Same content with different external_id → detected as duplicate."""
        obj_1 = _make_knowledge_object(external_id="id_1", content="Same content")
        store.save_objects([obj_1])

        # Different external_id but same content
        obj_2 = _make_knowledge_object(external_id="id_2", content="Same content")
        created = store.save_objects([obj_2])

        # Should be treated as update (content_hash match), not create
        assert created == 0
        assert store.count() == 1


# ==============================================================================
# Persistence Tests
# ==============================================================================


class TestPersistence:
    """Tests for JSON file persistence."""

    def test_persist_and_reload(self, storage_path: Path) -> None:
        """Objects survive store recreation from the same file."""
        store1 = FileKnowledgeStore(file_path=storage_path)
        obj = _make_knowledge_object(external_id="persist_test")
        store1.save_objects([obj])

        # Create a new store instance pointing to the same file
        store2 = FileKnowledgeStore(file_path=storage_path)
        assert store2.count() == 1

        retrieved = store2.get_by_external_id("persist_test", "rss")
        assert retrieved is not None
        assert retrieved.title == "Test Title"

    def test_empty_file_handling(self, storage_path: Path) -> None:
        """Store handles empty file gracefully."""
        storage_path.write_text("", encoding="utf-8")
        store = FileKnowledgeStore(file_path=storage_path)
        assert store.count() == 0

    def test_corrupted_file_handling(self, storage_path: Path) -> None:
        """Store handles corrupted JSON gracefully."""
        storage_path.write_text("{invalid json!!!", encoding="utf-8")
        store = FileKnowledgeStore(file_path=storage_path)
        assert store.count() == 0

    def test_missing_file_handling(self, tmp_path: Path) -> None:
        """Store handles missing file gracefully."""
        missing_path = tmp_path / "nonexistent" / "store.json"
        store = FileKnowledgeStore(file_path=missing_path)
        assert store.count() == 0

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        """Store creates parent directories if they don't exist."""
        nested_path = tmp_path / "deep" / "nested" / "store.json"
        store = FileKnowledgeStore(file_path=nested_path)
        obj = _make_knowledge_object()
        store.save_objects([obj])

        assert nested_path.exists()
