"""Unit tests for QdrantVectorStore update operations.

Covers update_vector, delete_by_knowledge_ids, and reindex_collection.
"""

from unittest.mock import MagicMock, patch

import pytest

from app.storage.vector.qdrant_store import QdrantVectorStore


@pytest.fixture
def mock_qdrant_client():
    """Create a mock QdrantClient."""
    with patch("app.storage.vector.qdrant_store.QdrantClient") as mock_class:
        mock_client = MagicMock()
        mock_class.return_value = mock_client
        yield mock_client


@pytest.fixture
def store(mock_qdrant_client) -> QdrantVectorStore:
    """Create a QdrantVectorStore with mocked client."""
    return QdrantVectorStore(dimensions=768)


class TestUpdateVector:
    """Tests for update_vector method."""

    def test_update_vector_with_new_payload(
        self, store: QdrantVectorStore, mock_qdrant_client
    ) -> None:
        """update_vector updates both vector and payload."""
        new_vector = [0.5] * 768
        new_payload = {"title": "Updated Title", "topics": ["AI"]}

        result = store.update_vector("point_001", new_vector, new_payload)

        assert result is True
        mock_qdrant_client.upsert.assert_called_once()

        # Verify the upserted point has new values
        call_args = mock_qdrant_client.upsert.call_args
        points = call_args[1]["points"]
        assert len(points) == 1
        assert points[0].id == "point_001"
        assert points[0].vector == new_vector
        assert points[0].payload == new_payload

    def test_update_vector_keeps_existing_payload(
        self, store: QdrantVectorStore, mock_qdrant_client
    ) -> None:
        """update_vector with None payload keeps existing payload."""
        # Mock get_point to return existing point
        mock_point = MagicMock()
        mock_point.id = "point_001"
        mock_point.vector = [0.1] * 768
        mock_point.payload = {"title": "Original", "topics": ["ML"]}
        mock_qdrant_client.retrieve.return_value = [mock_point]

        new_vector = [0.5] * 768
        result = store.update_vector("point_001", new_vector, None)

        assert result is True
        # Verify payload was preserved
        call_args = mock_qdrant_client.upsert.call_args
        points = call_args[1]["points"]
        assert points[0].payload == {"title": "Original", "topics": ["ML"]}

    def test_update_vector_nonexistent_point(
        self, store: QdrantVectorStore, mock_qdrant_client
    ) -> None:
        """update_vector returns False if point doesn't exist and payload is None."""
        mock_qdrant_client.retrieve.return_value = []

        result = store.update_vector("nonexistent", [0.5] * 768, None)

        assert result is False


class TestDeleteByKnowledgeIds:
    """Tests for delete_by_knowledge_ids method."""

    def test_delete_multiple_ids(self, store: QdrantVectorStore, mock_qdrant_client) -> None:
        """delete_by_knowledge_ids deletes multiple points."""
        ids = ["id_001", "id_002", "id_003"]
        count = store.delete_by_knowledge_ids(ids)

        assert count == 3
        mock_qdrant_client.delete.assert_called_once()

    def test_delete_empty_list(self, store: QdrantVectorStore, mock_qdrant_client) -> None:
        """delete_by_knowledge_ids with empty list returns 0."""
        count = store.delete_by_knowledge_ids([])

        assert count == 0
        mock_qdrant_client.delete.assert_not_called()


class TestReindexCollection:
    """Tests for reindex_collection method."""

    def test_reindex_clears_all_points(self, store: QdrantVectorStore, mock_qdrant_client) -> None:
        """reindex_collection deletes all points."""
        # Mock count to return 50
        mock_info = MagicMock()
        mock_info.points_count = 50
        mock_qdrant_client.get_collection.return_value = mock_info

        cleared = store.reindex_collection()

        assert cleared == 50
        mock_qdrant_client.delete.assert_called_once()

    def test_reindex_empty_collection(self, store: QdrantVectorStore, mock_qdrant_client) -> None:
        """reindex_collection on empty collection returns 0."""
        mock_info = MagicMock()
        mock_info.points_count = 0
        mock_qdrant_client.get_collection.return_value = mock_info

        cleared = store.reindex_collection()

        assert cleared == 0
