"""Unit tests for QdrantVectorStore.

All tests mock qdrant-client to avoid requiring a running Qdrant instance.
"""

from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from qdrant_client.http.exceptions import UnexpectedResponse

from app.storage.knowledge.base import CircuitBreaker
from app.storage.vector.base import VectorPoint
from app.storage.vector.qdrant_store import QdrantVectorStore, VectorStoreError

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_qdrant_client():
    """Create a mock QdrantClient."""
    with patch("app.storage.vector.qdrant_store.QdrantClient") as mock_class:
        mock_client = MagicMock()
        mock_class.return_value = mock_client
        yield mock_client


@pytest.fixture
def store(mock_qdrant_client) -> Generator[QdrantVectorStore, Any, None]:
    """Create a QdrantVectorStore with mocked client."""
    s = QdrantVectorStore(dimensions=768)
    yield s


def _make_point(point_id: str = "point_001") -> VectorPoint:
    """Create a test VectorPoint."""
    return VectorPoint(
        id=point_id,
        vector=[0.1] * 768,
        payload={
            "source_type": "rss",
            "source_name": "techcrunch",
            "external_id": "ext_001",
            "content_hash": "abc123",
            "title": "Test Title",
            "source_url": "https://example.com/article",
            "published_at": "2025-01-01T00:00:00",
            "topics": ["AI", "ML"],
            "entities": ["OpenAI"],
        },
    )


# =============================================================================
# Collection Management Tests
# =============================================================================


class TestCollectionManagement:
    """Tests for collection management operations."""

    def test_collection_exists_true(self, store: QdrantVectorStore, mock_qdrant_client) -> None:
        """collection_exists returns True when collection exists."""
        mock_collection = MagicMock()
        mock_collection.name = "knowledge_objects"
        mock_qdrant_client.get_collections.return_value.collections = [mock_collection]

        assert store.collection_exists() is True

    def test_collection_exists_false(self, store: QdrantVectorStore, mock_qdrant_client) -> None:
        """collection_exists returns False when collection doesn't exist."""
        mock_qdrant_client.get_collections.return_value.collections = []

        assert store.collection_exists() is False

    def test_create_collection_success(self, store: QdrantVectorStore, mock_qdrant_client) -> None:
        """create_collection creates collection with correct dimensions."""
        store.create_collection(dimensions=768)

        mock_qdrant_client.create_collection.assert_called_once()
        call_kwargs = mock_qdrant_client.create_collection.call_args[1]
        assert call_kwargs["collection_name"] == "knowledge_objects"

    def test_create_collection_already_exists(
        self, store: QdrantVectorStore, mock_qdrant_client
    ) -> None:
        """create_collection handles 409 (already exists) gracefully."""
        mock_qdrant_client.create_collection.side_effect = UnexpectedResponse(
            status_code=409,
            reason_phrase="Conflict",
            content=b"Collection already exists",
            headers={},
        )

        # Should not raise
        store.create_collection(dimensions=768)

    def test_create_collection_without_dimensions(self, store: QdrantVectorStore) -> None:
        """create_collection raises error if dimensions not specified."""
        store_no_dims = QdrantVectorStore(dimensions=None)

        with pytest.raises(VectorStoreError, match="dimensions not specified"):
            store_no_dims.create_collection()

    def test_ensure_collection_creates_if_missing(
        self, store: QdrantVectorStore, mock_qdrant_client
    ) -> None:
        """ensure_collection creates collection if it doesn't exist."""
        mock_qdrant_client.get_collections.return_value.collections = []

        store.ensure_collection(dimensions=768)

        mock_qdrant_client.create_collection.assert_called_once()


# =============================================================================
# Upsert Tests
# =============================================================================


class TestUpsertPoints:
    """Tests for upsert_points method."""

    def test_upsert_single_point(self, store: QdrantVectorStore, mock_qdrant_client) -> None:
        """Upsert single point returns 1."""
        point = _make_point()
        count = store.upsert_points([point])

        assert count == 1
        mock_qdrant_client.upsert.assert_called_once()

    def test_upsert_empty_list(self, store: QdrantVectorStore, mock_qdrant_client) -> None:
        """Upsert empty list returns 0."""
        count = store.upsert_points([])

        assert count == 0
        mock_qdrant_client.upsert.assert_not_called()

    def test_upsert_batch_splitting(self, store: QdrantVectorStore, mock_qdrant_client) -> None:
        """Large batches are split into chunks of 100."""
        points = [_make_point(f"point_{i}") for i in range(150)]
        count = store.upsert_points(points)

        assert count == 150
        assert mock_qdrant_client.upsert.call_count == 2  # 100 + 50

    def test_upsert_idempotent(self, store: QdrantVectorStore, mock_qdrant_client) -> None:
        """Upserting same ID twice overwrites (Qdrant native behavior)."""
        point_v1 = VectorPoint(id="abc", vector=[0.1] * 768, payload={"version": 1})
        point_v2 = VectorPoint(id="abc", vector=[0.2] * 768, payload={"version": 2})

        store.upsert_points([point_v1])
        store.upsert_points([point_v2])

        assert mock_qdrant_client.upsert.call_count == 2

    def test_upsert_circuit_open(self, mock_qdrant_client) -> None:
        """Upsert raises error when circuit breaker is open."""
        cb = CircuitBreaker(failure_threshold=1)
        cb.record_failure()  # Open circuit

        store = QdrantVectorStore(dimensions=768, circuit_breaker=cb)

        with pytest.raises(VectorStoreError, match="circuit breaker is open"):
            store.upsert_points([_make_point()])


# =============================================================================
# Delete Tests
# =============================================================================


class TestDeletePoints:
    """Tests for delete_points method."""

    def test_delete_single_point(self, store: QdrantVectorStore, mock_qdrant_client) -> None:
        """Delete single point returns 1."""
        count = store.delete_points(["point_001"])

        assert count == 1
        mock_qdrant_client.delete.assert_called_once()

    def test_delete_empty_list(self, store: QdrantVectorStore, mock_qdrant_client) -> None:
        """Delete empty list returns 0."""
        count = store.delete_points([])

        assert count == 0
        mock_qdrant_client.delete.assert_not_called()

    def test_delete_multiple_points(self, store: QdrantVectorStore, mock_qdrant_client) -> None:
        """Delete multiple points returns count."""
        ids = ["point_001", "point_002", "point_003"]
        count = store.delete_points(ids)

        assert count == 3


# =============================================================================
# Get Point Tests
# =============================================================================


class TestGetPoint:
    """Tests for get_point method."""

    def test_get_point_found(self, store: QdrantVectorStore, mock_qdrant_client) -> None:
        """get_point returns VectorPoint when found."""
        mock_point = MagicMock()
        mock_point.id = "point_001"
        mock_point.vector = [0.1] * 768
        mock_point.payload = {"title": "Test"}
        mock_qdrant_client.retrieve.return_value = [mock_point]

        result = store.get_point("point_001")

        assert result is not None
        assert result.id == "point_001"
        assert result.payload["title"] == "Test"

    def test_get_point_not_found(self, store: QdrantVectorStore, mock_qdrant_client) -> None:
        """get_point returns None when not found."""
        mock_qdrant_client.retrieve.return_value = []

        result = store.get_point("nonexistent")

        assert result is None


# =============================================================================
# Payload Structure Tests
# =============================================================================


class TestPayloadStructure:
    """Tests for payload structure compliance."""

    def test_payload_has_required_fields(
        self, store: QdrantVectorStore, mock_qdrant_client
    ) -> None:
        """Payload contains all required fields for filtering."""
        point = _make_point()
        store.upsert_points([point])

        # Verify the payload passed to Qdrant
        call_args = mock_qdrant_client.upsert.call_args
        points_arg = call_args[1]["points"]
        payload = points_arg[0].payload

        required_fields = [
            "source_type",
            "source_name",
            "external_id",
            "content_hash",
            "title",
            "source_url",
            "published_at",
            "topics",
            "entities",
        ]

        for field in required_fields:
            assert field in payload, f"Missing required field: {field}"

    def test_payload_topics_is_list(self, store: QdrantVectorStore, mock_qdrant_client) -> None:
        """Topics field is a list for multi-value filtering."""
        point = _make_point()
        store.upsert_points([point])

        call_args = mock_qdrant_client.upsert.call_args
        points_arg = call_args[1]["points"]
        payload = points_arg[0].payload

        assert isinstance(payload["topics"], list)
        assert isinstance(payload["entities"], list)


# =============================================================================
# Reliability Tests
# =============================================================================


class TestReliability:
    """Tests for retry and circuit breaker behavior."""

    def test_retry_on_transient_error(self, mock_qdrant_client) -> None:
        """Retries on transient error."""
        mock_qdrant_client.upsert.side_effect = [
            Exception("Connection timeout"),
            Exception("Connection timeout"),
            None,  # Success on third try
        ]

        store = QdrantVectorStore(dimensions=768)
        count = store.upsert_points([_make_point()])

        assert count == 1
        assert mock_qdrant_client.upsert.call_count == 3

    def test_circuit_opens_after_failures(self, mock_qdrant_client) -> None:
        """Circuit breaker opens after consecutive failures."""
        cb = CircuitBreaker(failure_threshold=2)
        store = QdrantVectorStore(dimensions=768, circuit_breaker=cb)

        mock_qdrant_client.upsert.side_effect = Exception("Qdrant down")

        # First call fails
        with pytest.raises(VectorStoreError):
            store.upsert_points([_make_point()])

        # Second call fails
        with pytest.raises(VectorStoreError):
            store.upsert_points([_make_point()])

        # Circuit should now be open
        with pytest.raises(VectorStoreError, match="circuit breaker is open"):
            store.upsert_points([_make_point()])

    def test_circuit_recovers_after_timeout(self, mock_qdrant_client) -> None:
        """Circuit breaker allows request after recovery timeout."""
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.1)
        store = QdrantVectorStore(dimensions=768, circuit_breaker=cb)

        mock_qdrant_client.upsert.side_effect = Exception("Qdrant down")

        # Trip the circuit
        with pytest.raises(VectorStoreError):
            store.upsert_points([_make_point()])

        # Wait for recovery timeout
        import time

        time.sleep(0.2)

        # Circuit should be half-open, allow request
        mock_qdrant_client.upsert.side_effect = None  # Reset
        mock_qdrant_client.upsert.return_value = None

        # This should not raise circuit open error
        # (may still fail due to mock, but not due to circuit)
        try:
            store.upsert_points([_make_point()])
        except VectorStoreError as e:
            assert "circuit breaker is open" not in str(e)
