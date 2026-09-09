"""Performance smoke tests for Qdrant vector indexing.

These tests use mocked Qdrant client and validate batching throughput.
Real Qdrant retrieval benchmark is located in:
tests/performance/test_retrieval_benchmark.py
"""

import time
from unittest.mock import MagicMock, patch

import pytest

from app.storage.vector.base import VectorPoint
from app.storage.vector.qdrant_store import QdrantVectorStore


@pytest.fixture
def mock_qdrant_client():
    """Create a mock QdrantClient."""
    with patch("app.storage.vector.qdrant_store.QdrantClient") as mock_class:
        mock_client = MagicMock()
        mock_class.return_value = mock_client
        yield mock_client


class TestVectorUpsertPerformance:
    """Performance smoke tests for vector upsert batching."""

    def test_upsert_10k_points_batching_performance(self, mock_qdrant_client: MagicMock) -> None:
        """10k points are split into 100 batches and processed quickly."""
        store = QdrantVectorStore(dimensions=8)

        points = [
            VectorPoint(
                id=f"point_{i}",
                vector=[0.1] * 8,
                payload={"index": i},
            )
            for i in range(10_000)
        ]

        start = time.perf_counter()
        count = store.upsert_points(points)
        elapsed = time.perf_counter() - start

        assert count == 10_000
        assert mock_qdrant_client.upsert.call_count == 100
        # 5.0s threshold: pydantic PointStruct validation for 10k objects
        # takes 2-4s depending on machine. This catches major regressions
        # without being flaky on slower dev machines.
        assert elapsed < 5.0

    def test_upsert_empty_batch_is_fast(self, mock_qdrant_client: MagicMock) -> None:
        """Empty batch returns immediately."""
        store = QdrantVectorStore(dimensions=8)

        start = time.perf_counter()
        count = store.upsert_points([])
        elapsed = time.perf_counter() - start

        assert count == 0
        assert mock_qdrant_client.upsert.call_count == 0
        assert elapsed < 0.1
