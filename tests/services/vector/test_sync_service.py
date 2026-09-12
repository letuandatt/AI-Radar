"""Unit tests for VectorSyncService (T149).

Covers sync_knowledge_object, delete_orphaned_vectors, and full_reindex.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from app.core.utils import compute_text_hash
from app.models.knowledge_object import KnowledgeObject
from app.models.metadata import ExtractionResult
from app.services.embedding.context_builder import ContextBuilder
from app.services.vector.sync_service import VectorSyncService
from app.storage.vector.qdrant_store import QdrantVectorStore


@pytest.fixture
def mock_vector_store() -> QdrantVectorStore:
    """Create a mock QdrantVectorStore."""
    store = MagicMock(spec=QdrantVectorStore)
    store.build_payload = QdrantVectorStore.build_payload.__get__(store, QdrantVectorStore)
    return store


@pytest.fixture
def mock_context_builder() -> ContextBuilder:
    """Create a mock ContextBuilder."""
    builder = MagicMock(spec=ContextBuilder)
    builder.build_for_embedding.return_value = "[CCH Header]\nTest content"
    builder.build_batch_for_embedding.return_value = [
        "[CCH 1]\nContent 1",
        "[CCH 2]\nContent 2",
    ]
    return builder


@pytest.fixture
def sync_service(mock_vector_store, mock_context_builder) -> VectorSyncService:
    """Create a VectorSyncService with mocks."""
    return VectorSyncService(
        vector_store=mock_vector_store,
        context_builder=mock_context_builder,
    )


def _make_ko(
    obj_id: str = "ko_001",
    content: str = "Test content",
) -> KnowledgeObject:
    """Create a test KnowledgeObject."""
    metadata = ExtractionResult(
        summary="Summary",
        topics=["AI", "ML"],
        entities=["OpenAI"],
        relevance_score=0.9,
    )
    ko = KnowledgeObject(
        source_type="rss",
        source_name="techcrunch",
        external_id="ext_001",
        source_url="https://example.com/article",
        content_hash=compute_text_hash(content),
        fetched_at=datetime(2025, 1, 2, tzinfo=timezone.utc),
        published_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        title="Test Title",
        content_text=content,
        metadata=metadata,
    )
    ko.id = obj_id
    return ko


class TestSyncKnowledgeObject:
    """Tests for sync_knowledge_object method."""

    def test_sync_single_object(
        self,
        sync_service: VectorSyncService,
        mock_vector_store,
        mock_context_builder,
    ) -> None:
        """sync_knowledge_object builds CCH, embeds, and upserts."""
        mock_provider = MagicMock()
        mock_provider.embed_text.return_value = [0.1] * 768
        mock_vector_store.upsert_points.return_value = 1

        ko = _make_ko()
        result = sync_service.sync_knowledge_object(ko, mock_provider)

        assert result is True
        mock_context_builder.build_for_embedding.assert_called_once_with(ko)
        mock_provider.embed_text.assert_called_once()
        mock_vector_store.upsert_points.assert_called_once()

    def test_sync_builds_correct_payload(
        self,
        sync_service: VectorSyncService,
        mock_vector_store,
    ) -> None:
        """sync_knowledge_object builds payload with all required fields."""
        mock_provider = MagicMock()
        mock_provider.embed_text.return_value = [0.1] * 768
        mock_vector_store.upsert_points.return_value = 1

        ko = _make_ko()
        sync_service.sync_knowledge_object(ko, mock_provider)

        # Verify upserted point has correct payload
        call_args = mock_vector_store.upsert_points.call_args
        points = call_args[0][0]
        assert len(points) == 1
        point = points[0]
        assert point.id == ko.id
        assert point.payload["source_type"] == "rss"
        assert point.payload["source_name"] == "techcrunch"
        assert point.payload["title"] == "Test Title"
        assert "AI" in point.payload["topics"]


class TestDeleteOrphanedVectors:
    """Tests for delete_orphaned_vectors method."""

    def test_delete_orphaned_vectors(
        self, sync_service: VectorSyncService, mock_vector_store
    ) -> None:
        """delete_orphaned_vectors deletes points not in valid_ids."""
        # Qdrant has 5 points: ko_001, ko_002, ko_003, ko_004, ko_005
        mock_vector_store.get_all_point_ids.return_value = [
            "ko_001",
            "ko_002",
            "ko_003",
            "ko_004",
            "ko_005",
        ]
        # Only ko_001, ko_002, ko_003 exist in SQLite
        valid_ids = {"ko_001", "ko_002", "ko_003"}
        mock_vector_store.delete_by_knowledge_ids.return_value = 2

        deleted = sync_service.delete_orphaned_vectors(valid_ids)

        assert deleted == 2
        # Verify orphaned IDs were identified correctly
        call_args = mock_vector_store.delete_by_knowledge_ids.call_args
        deleted_ids = call_args[0][0]
        assert set(deleted_ids) == {"ko_004", "ko_005"}

    def test_delete_orphaned_no_orphans(
        self, sync_service: VectorSyncService, mock_vector_store
    ) -> None:
        """delete_orphaned_vectors returns 0 when no orphans exist."""
        mock_vector_store.get_all_point_ids.return_value = ["ko_001", "ko_002"]
        valid_ids = {"ko_001", "ko_002"}

        deleted = sync_service.delete_orphaned_vectors(valid_ids)

        assert deleted == 0
        mock_vector_store.delete_by_knowledge_ids.assert_not_called()

    def test_delete_orphaned_all_orphaned(
        self, sync_service: VectorSyncService, mock_vector_store
    ) -> None:
        """delete_orphaned_vectors deletes all when valid_ids is empty."""
        mock_vector_store.get_all_point_ids.return_value = ["ko_001", "ko_002"]
        valid_ids = set()
        mock_vector_store.delete_by_knowledge_ids.return_value = 2

        deleted = sync_service.delete_orphaned_vectors(valid_ids)

        assert deleted == 2


class TestFullReindex:
    """Tests for full_reindex method."""

    def test_full_reindex_rebuilds_all(
        self,
        sync_service: VectorSyncService,
        mock_vector_store,
        mock_context_builder,
    ) -> None:
        """full_reindex clears collection and reindexes all objects."""
        # Mock SQLite store with 3 objects
        mock_sqlite_store = MagicMock()
        ko1 = _make_ko("ko_001", "Content 1")
        ko2 = _make_ko("ko_002", "Content 2")
        ko3 = _make_ko("ko_003", "Content 3")
        mock_sqlite_store.get_all.return_value = [ko1, ko2, ko3]

        # Mock vector store operations
        mock_vector_store.reindex_collection.return_value = 10
        mock_vector_store.upsert_points.return_value = 3

        # Mock embedding provider
        mock_provider = MagicMock()
        mock_provider.embed_batch.return_value = [
            [0.1] * 768,
            [0.2] * 768,
            [0.3] * 768,
        ]

        reindexed = sync_service.full_reindex(mock_sqlite_store, mock_provider, batch_size=10)

        assert reindexed == 3
        mock_vector_store.reindex_collection.assert_called_once()
        mock_vector_store.upsert_points.assert_called_once()

    def test_full_reindex_empty_store(
        self,
        sync_service: VectorSyncService,
        mock_vector_store,
    ) -> None:
        """full_reindex returns 0 when SQLite store is empty."""
        mock_sqlite_store = MagicMock()
        mock_sqlite_store.get_all.return_value = []
        mock_vector_store.reindex_collection.return_value = 5

        mock_provider = MagicMock()

        reindexed = sync_service.full_reindex(mock_sqlite_store, mock_provider)

        assert reindexed == 0
        mock_vector_store.upsert_points.assert_not_called()

    def test_full_reindex_batch_splitting(
        self,
        sync_service: VectorSyncService,
        mock_vector_store,
        mock_context_builder,
    ) -> None:
        """full_reindex splits large dataset into batches."""
        # Create 150 objects
        objects = [_make_ko(f"ko_{i:03d}", f"Content {i}") for i in range(150)]

        mock_sqlite_store = MagicMock()
        mock_sqlite_store.get_all.return_value = objects

        mock_vector_store.reindex_collection.return_value = 0
        mock_vector_store.upsert_points.side_effect = lambda points: len(points)

        # Embed batch returns one vector per input text
        mock_provider = MagicMock()
        mock_provider.embed_batch.side_effect = lambda texts: [[0.1] * 768 for _ in texts]

        # Context builder returns one CCH text per object
        mock_context_builder.build_batch_for_embedding.side_effect = lambda batch: [
            f"[CCH {obj.id}]\n{obj.content_text}" for obj in batch
        ]

        reindexed = sync_service.full_reindex(
            mock_sqlite_store,
            mock_provider,
            batch_size=100,
        )

        assert reindexed == 150
        assert mock_provider.embed_batch.call_count == 2
        assert mock_vector_store.upsert_points.call_count == 2
