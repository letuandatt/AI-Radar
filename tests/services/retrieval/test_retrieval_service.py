"""Unit tests for RetrievalService (T167)."""

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from app.core.utils import compute_text_hash
from app.models.knowledge_object import KnowledgeObject
from app.models.metadata import ExtractionResult
from app.services.retrieval.retrieval_models import (
    InvalidRetrievalMethodError,
    RetrievalQueryTooLongError,
    RetrievalResponse,
    RetrievalServiceUnavailableError,
)
from app.services.retrieval.retrieval_service import RetrievalService
from app.services.retrieval.vector_search import VectorSearchResult

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_vector_search():
    """Create a mock VectorSearchService."""
    service = MagicMock()
    service.search.return_value = []
    service.search_by_vector.return_value = []
    service.get_vector.return_value = None
    return service


@pytest.fixture
def mock_fusion_retriever():
    """Create a mock FusionRetriever."""
    retriever = MagicMock()
    retriever.hybrid_search.return_value = []
    return retriever


@pytest.fixture
def mock_bm25_index():
    """Create a mock BM25Index."""
    index = MagicMock()
    index.search.return_value = []
    return index


@pytest.fixture
def mock_sqlite_store():
    """Create a mock SQLiteKnowledgeStore."""
    store = MagicMock()
    store.get_by_id.return_value = None
    return store


@pytest.fixture
def service(mock_vector_search, mock_fusion_retriever, mock_bm25_index, mock_sqlite_store):
    """Create a RetrievalService with mocks."""
    return RetrievalService(
        vector_search=mock_vector_search,
        fusion_retriever=mock_fusion_retriever,
        bm25_index=mock_bm25_index,
        sqlite_store=mock_sqlite_store,
    )


def _make_ko(
    obj_id: str = "ko_001",
    title: str = "Test Article",
    content: str = "Test content for the article.",
    source_type: str = "rss",
    source_name: str = "techcrunch",
) -> KnowledgeObject:
    """Helper to create a KnowledgeObject."""
    metadata = ExtractionResult(
        summary="Summary",
        topics=["AI", "ML"],
        entities=["OpenAI"],
        relevance_score=0.9,
    )
    ko = KnowledgeObject(
        source_type=source_type,
        source_name=source_name,
        external_id=f"ext_{obj_id}",
        source_url=f"https://example.com/{obj_id}",
        content_hash=compute_text_hash(content),
        fetched_at=datetime(2025, 1, 2, tzinfo=timezone.utc),
        published_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        title=title,
        content_text=content,
        metadata=metadata,
    )
    ko.id = obj_id
    return ko


# =============================================================================
# Strategy Dispatch Tests
# =============================================================================


class TestStrategyDispatch:
    """Tests for retrieval method dispatch."""

    def test_vector_method_calls_vector_search(self, service, mock_vector_search) -> None:
        """method='vector' only calls vector search."""
        service.search("test query", method="vector")
        mock_vector_search.search.assert_called_once()

    def test_keyword_method_calls_bm25(self, service, mock_bm25_index) -> None:
        """method='keyword' only calls BM25 search."""
        service.search("test query", method="keyword")
        mock_bm25_index.search.assert_called_once()

    def test_hybrid_method_calls_fusion(self, service, mock_fusion_retriever) -> None:
        """method='hybrid' calls fusion retriever."""
        service.search("test query", method="hybrid")
        mock_fusion_retriever.hybrid_search.assert_called_once()

    def test_default_method_is_hybrid(self, service, mock_fusion_retriever) -> None:
        """Default method is 'hybrid'."""
        service.search("test query")
        mock_fusion_retriever.hybrid_search.assert_called_once()

    def test_invalid_method_raises_error(self, service) -> None:
        """Invalid method raises InvalidRetrievalMethodError."""
        with pytest.raises(InvalidRetrievalMethodError):
            service.search("test query", method="invalid_method")


# =============================================================================
# Response Structure Tests
# =============================================================================


class TestResponseStructure:
    """Tests for retrieval response structure."""

    def test_response_has_required_fields(
        self, service, mock_vector_search, mock_sqlite_store
    ) -> None:
        """Response contains all required fields."""
        ko = _make_ko()
        mock_sqlite_store.get_by_id.return_value = ko
        mock_vector_search.search.return_value = [
            VectorSearchResult(knowledge_id="ko_001", score=0.95, payload={}),
        ]

        response = service.search("test query", method="vector")

        assert isinstance(response, RetrievalResponse)
        assert response.query == "test query"
        assert response.total_matches == 1
        assert response.retrieval_time_ms > 0
        assert response.method == "vector"

    def test_result_has_citations(self, service, mock_vector_search, mock_sqlite_store) -> None:
        """Results include source_url and knowledge_id citations."""
        ko = _make_ko()
        mock_sqlite_store.get_by_id.return_value = ko
        mock_vector_search.search.return_value = [
            VectorSearchResult(knowledge_id="ko_001", score=0.95, payload={}),
        ]

        response = service.search("test query", method="vector")

        assert len(response.results) == 1
        result = response.results[0]
        assert result.knowledge_id == "ko_001"
        assert result.source_url == "https://example.com/ko_001"
        assert result.title == "Test Article"

    def test_result_has_metadata(self, service, mock_vector_search, mock_sqlite_store) -> None:
        """Results include topics, entities, and snippet."""
        ko = _make_ko()
        mock_sqlite_store.get_by_id.return_value = ko
        mock_vector_search.search.return_value = [
            VectorSearchResult(knowledge_id="ko_001", score=0.95, payload={}),
        ]

        response = service.search("test query", method="vector")

        result = response.results[0]
        assert result.topics == ["AI", "ML"]
        assert result.entities == ["OpenAI"]
        assert result.content_snippet == "Test content for the article."
        assert result.source_type == "rss"
        assert result.source_name == "techcrunch"

    def test_result_retrieval_method_reflects_strategy(
        self, service, mock_vector_search, mock_sqlite_store
    ) -> None:
        """retrieval_method field reflects the strategy used."""
        ko = _make_ko()
        mock_sqlite_store.get_by_id.return_value = ko
        mock_vector_search.search.return_value = [
            VectorSearchResult(knowledge_id="ko_001", score=0.95, payload={}),
        ]

        response = service.search("test query", method="vector")
        assert response.results[0].retrieval_method == "vector"

    def test_content_snippet_truncated(
        self, service, mock_vector_search, mock_sqlite_store
    ) -> None:
        """Content snippet is truncated to 300 chars."""
        long_content = "x" * 500
        ko = _make_ko(content=long_content)
        mock_sqlite_store.get_by_id.return_value = ko
        mock_vector_search.search.return_value = [
            VectorSearchResult(knowledge_id="ko_001", score=0.95, payload={}),
        ]

        response = service.search("test query", method="vector")
        assert len(response.results[0].content_snippet) == 300

    def test_filters_applied_in_response(
        self, service, mock_vector_search, mock_sqlite_store
    ) -> None:
        """filters_applied is populated when filter is provided."""
        from app.services.retrieval.filter_models import MetadataFilter

        ko = _make_ko()
        mock_sqlite_store.get_by_id.return_value = ko
        mock_vector_search.search.return_value = [
            VectorSearchResult(knowledge_id="ko_001", score=0.95, payload={}),
        ]

        metadata_filter = MetadataFilter(source_type="github")
        response = service.search(
            "test query",
            metadata_filter=metadata_filter,
            method="vector",
        )

        assert response.filters_applied is not None
        assert response.filters_applied["source_type"] == "github"


# =============================================================================
# Error Contract Tests
# =============================================================================


class TestErrorContract:
    """Tests for retrieval error contract."""

    def test_query_too_long_raises_error(self, service) -> None:
        """Query > 1000 chars raises RetrievalQueryTooLongError."""
        long_query = "x" * 1001
        with pytest.raises(RetrievalQueryTooLongError):
            service.search(long_query)

    def test_query_at_max_length_ok(self, service) -> None:
        """Query exactly 1000 chars is accepted."""
        query = "x" * 1000
        # Should not raise
        response = service.search(query)
        assert response.query == query

    def test_invalid_method_raises_error(self, service) -> None:
        """Invalid method raises InvalidRetrievalMethodError."""
        with pytest.raises(InvalidRetrievalMethodError) as exc_info:
            service.search("test", method="semantic")

        assert "semantic" in str(exc_info.value)

    def test_service_unavailable_on_search_failure(self, service, mock_vector_search) -> None:
        """Search failure raises RetrievalServiceUnavailableError."""
        mock_vector_search.search.side_effect = Exception("Qdrant down")

        with pytest.raises(RetrievalServiceUnavailableError):
            service.search("test query", method="vector")

    def test_missing_knowledge_object_skipped(
        self, service, mock_vector_search, mock_sqlite_store
    ) -> None:
        """Results with missing KnowledgeObject in SQLite are skipped."""
        mock_sqlite_store.get_by_id.return_value = None
        mock_vector_search.search.return_value = [
            VectorSearchResult(knowledge_id="nonexistent", score=0.95, payload={}),
        ]

        response = service.search("test query", method="vector")
        assert response.total_matches == 0
        assert len(response.results) == 0


# =============================================================================
# Related Items Tests
# =============================================================================


class TestGetRelatedItems:
    """Tests for get_related_items method."""

    def test_get_related_items_success(
        self, service, mock_vector_search, mock_sqlite_store
    ) -> None:
        """get_related_items returns related items."""
        original_ko = _make_ko("ko_001", title="Original")
        related_ko = _make_ko("ko_002", title="Related")

        def get_by_id_side_effect(obj_id):
            if obj_id == "ko_001":
                return original_ko
            elif obj_id == "ko_002":
                return related_ko
            return None

        mock_sqlite_store.get_by_id.side_effect = get_by_id_side_effect
        mock_vector_search.get_vector.return_value = [0.1] * 768
        mock_vector_search.search_by_vector.return_value = [
            VectorSearchResult(knowledge_id="ko_001", score=1.0, payload={}),
            VectorSearchResult(knowledge_id="ko_002", score=0.9, payload={}),
        ]

        response = service.get_related_items("ko_001", top_k=5)

        assert response.total_matches == 1
        assert response.results[0].knowledge_id == "ko_002"

    def test_get_related_items_excludes_original(
        self, service, mock_vector_search, mock_sqlite_store
    ) -> None:
        """get_related_items excludes the original item."""
        original_ko = _make_ko("ko_001")
        mock_sqlite_store.get_by_id.return_value = original_ko
        mock_vector_search.get_vector.return_value = [0.1] * 768
        mock_vector_search.search_by_vector.return_value = [
            VectorSearchResult(knowledge_id="ko_001", score=1.0, payload={}),
        ]

        response = service.get_related_items("ko_001")

        # Original item should be excluded
        result_ids = [r.knowledge_id for r in response.results]
        assert "ko_001" not in result_ids

    def test_get_related_items_not_found(self, service, mock_sqlite_store) -> None:
        """get_related_items raises error for nonexistent item."""
        mock_sqlite_store.get_by_id.return_value = None

        with pytest.raises(RetrievalServiceUnavailableError):
            service.get_related_items("nonexistent")

    def test_get_related_items_no_vector(
        self, service, mock_vector_search, mock_sqlite_store
    ) -> None:
        """get_related_items raises error when vector not found."""
        ko = _make_ko()
        mock_sqlite_store.get_by_id.return_value = ko
        mock_vector_search.get_vector.return_value = None

        with pytest.raises(RetrievalServiceUnavailableError):
            service.get_related_items("ko_001")


# =============================================================================
# MCP-001 Readiness Tests
# =============================================================================


class TestMCP001Readiness:
    """Tests for MCP-001 readiness (JSON serialization)."""

    def test_response_serializable_to_json(
        self, service, mock_vector_search, mock_sqlite_store
    ) -> None:
        """RetrievalResponse can be serialized to JSON without errors."""
        ko = _make_ko()
        mock_sqlite_store.get_by_id.return_value = ko
        mock_vector_search.search.return_value = [
            VectorSearchResult(knowledge_id="ko_001", score=0.95, payload={}),
        ]

        response = service.search("test query", method="vector")

        # Should not raise
        json_str = response.model_dump_json()
        assert json_str is not None

        # Should be valid JSON
        parsed = json.loads(json_str)
        assert parsed["query"] == "test query"
        assert len(parsed["results"]) == 1

    def test_result_has_all_documented_fields(
        self, service, mock_vector_search, mock_sqlite_store
    ) -> None:
        """RetrievalResult has all fields documented for OpenAPI."""
        ko = _make_ko()
        mock_sqlite_store.get_by_id.return_value = ko
        mock_vector_search.search.return_value = [
            VectorSearchResult(knowledge_id="ko_001", score=0.95, payload={}),
        ]

        response = service.search("test query", method="vector")
        result = response.results[0]

        # All required fields for MCP-001
        assert hasattr(result, "knowledge_id")
        assert hasattr(result, "title")
        assert hasattr(result, "source_url")
        assert hasattr(result, "content_snippet")
        assert hasattr(result, "source_type")
        assert hasattr(result, "source_name")
        assert hasattr(result, "published_at")
        assert hasattr(result, "topics")
        assert hasattr(result, "entities")
        assert hasattr(result, "relevance_score")
        assert hasattr(result, "retrieval_method")
