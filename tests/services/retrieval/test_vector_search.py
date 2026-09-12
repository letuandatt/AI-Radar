"""Unit tests for VectorSearchService."""

from unittest.mock import MagicMock

import pytest

from app.services.retrieval.filter_models import MetadataFilter
from app.services.retrieval.vector_search import (
    VectorSearchResult,
    VectorSearchService,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_qdrant_store():
    """Create a mock QdrantVectorStore."""
    store = MagicMock()
    store.search_vectors.return_value = []
    return store


@pytest.fixture
def mock_embedding_provider():
    """Create a mock EmbeddingProvider."""
    provider = MagicMock()
    provider.embed_text.return_value = [0.1] * 768
    return provider


@pytest.fixture
def service(mock_qdrant_store, mock_embedding_provider):
    """Create a VectorSearchService with mocks."""
    return VectorSearchService(
        qdrant_store=mock_qdrant_store,
        embedding_provider=mock_embedding_provider,
    )


# =============================================================================
# Search Tests
# =============================================================================


class TestVectorSearch:
    """Tests for VectorSearchService.search method."""

    def test_search_calls_embedding_provider(self, service, mock_embedding_provider) -> None:
        """search() embeds the query text."""
        service.search("test query")
        mock_embedding_provider.embed_text.assert_called_once_with("test query")

    def test_search_calls_qdrant_with_vector(self, service, mock_qdrant_store) -> None:
        """search() calls Qdrant with the embedded vector."""
        service.search("test query")
        mock_qdrant_store.search_vectors.assert_called_once()

        call_kwargs = mock_qdrant_store.search_vectors.call_args[1]
        assert call_kwargs["query_vector"] == [0.1] * 768

    def test_search_returns_results(self, service, mock_qdrant_store) -> None:
        """search() returns VectorSearchResult list."""
        mock_qdrant_store.search_vectors.return_value = [
            {"id": "ko_1", "score": 0.95, "payload": {"title": "Test"}},
            {"id": "ko_2", "score": 0.85, "payload": {"title": "Test 2"}},
        ]

        results = service.search("test query")

        assert len(results) == 2
        assert isinstance(results[0], VectorSearchResult)
        assert results[0].knowledge_id == "ko_1"
        assert results[0].score == 0.95
        assert results[0].payload["title"] == "Test"

    def test_search_respects_top_k(self, service, mock_qdrant_store) -> None:
        """search() passes top_k as limit to Qdrant."""
        service.search("test query", top_k=5)

        call_kwargs = mock_qdrant_store.search_vectors.call_args[1]
        assert call_kwargs["limit"] == 5

    def test_search_empty_results(self, service, mock_qdrant_store) -> None:
        """search() returns empty list when no matches."""
        mock_qdrant_store.search_vectors.return_value = []
        results = service.search("no match query")
        assert results == []


# =============================================================================
# Filter Tests
# =============================================================================


class TestVectorSearchWithFilter:
    """Tests for vector search with metadata filtering."""

    def test_search_with_filter_builds_qdrant_filter(self, service, mock_qdrant_store) -> None:
        """search() builds Qdrant filter from MetadataFilter."""
        metadata_filter = MetadataFilter(source_type="github")
        service.search("test query", metadata_filter=metadata_filter)

        call_kwargs = mock_qdrant_store.search_vectors.call_args[1]
        assert call_kwargs["query_filter"] is not None

    def test_search_with_empty_filter_passes_none(self, service, mock_qdrant_store) -> None:
        """search() passes None filter for empty MetadataFilter."""
        metadata_filter = MetadataFilter()
        service.search("test query", metadata_filter=metadata_filter)

        call_kwargs = mock_qdrant_store.search_vectors.call_args[1]
        assert call_kwargs["query_filter"] is None

    def test_search_without_filter_passes_none(self, service, mock_qdrant_store) -> None:
        """search() passes None filter when no filter provided."""
        service.search("test query")

        call_kwargs = mock_qdrant_store.search_vectors.call_args[1]
        assert call_kwargs["query_filter"] is None


# =============================================================================
# search_by_vector Tests
# =============================================================================


class TestSearchByVector:
    """Tests for search_by_vector method."""

    def test_search_by_vector_uses_provided_vector(
        self, service, mock_qdrant_store, mock_embedding_provider
    ) -> None:
        """search_by_vector() uses the provided vector directly."""
        custom_vector = [0.5] * 768
        service.search_by_vector(vector=custom_vector)

        # Should NOT call embedding provider
        mock_embedding_provider.embed_text.assert_not_called()

        # Should use the custom vector
        call_kwargs = mock_qdrant_store.search_vectors.call_args[1]
        assert call_kwargs["query_vector"] == custom_vector

    def test_search_by_vector_returns_results(self, service, mock_qdrant_store) -> None:
        """search_by_vector() returns VectorSearchResult list."""
        mock_qdrant_store.search_vectors.return_value = [
            {"id": "ko_1", "score": 0.9, "payload": {}},
        ]

        results = service.search_by_vector(vector=[0.5] * 768)

        assert len(results) == 1
        assert results[0].knowledge_id == "ko_1"
