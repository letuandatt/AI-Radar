"""End-to-end integration tests for RetrievalService.

These tests validate the full retrieval pipeline with mocked
Qdrant and BM25, but real SQLite for metadata enrichment.
"""

import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.core.utils import compute_text_hash
from app.models.knowledge_object import KnowledgeObject
from app.models.metadata import ExtractionResult
from app.services.retrieval.filter_models import MetadataFilter
from app.services.retrieval.fusion_retriever import FusedResult
from app.services.retrieval.retrieval_service import RetrievalService
from app.services.retrieval.vector_search import VectorSearchResult
from app.storage.knowledge.sqlite_store import SQLiteKnowledgeStore

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def sqlite_store(tmp_path: Path) -> SQLiteKnowledgeStore:
    """Create a real SQLiteKnowledgeStore with test data."""
    store = SQLiteKnowledgeStore(db_path=tmp_path / "test.db")

    # Insert 100 test KnowledgeObjects
    objects = []
    for i in range(100):
        source_type = "rss" if i % 2 == 0 else "github"
        source_name = f"source_{i % 5}"
        title = f"Article about GPT-4o and AI {i}" if i < 20 else f"Article about topic {i}"
        content = (
            f"Content about GPT-4o model improvements and AI research {i}"
            if i < 20
            else f"Content about various technology topics {i}"
        )

        metadata = ExtractionResult(
            summary=f"Summary {i}",
            topics=["AI", "GPT"] if i < 20 else ["Tech"],
            entities=["OpenAI"] if i < 20 else [],
            relevance_score=0.9,
        )

        ko = KnowledgeObject(
            source_type=source_type,
            source_name=source_name,
            external_id=f"ext_{i}",
            source_url=f"https://example.com/article_{i}",
            content_hash=compute_text_hash(content),
            fetched_at=datetime.now(timezone.utc),
            published_at=datetime.now(timezone.utc) - timedelta(days=i % 60),
            title=title,
            content_text=content,
            metadata=metadata,
        )
        objects.append(ko)

    store.save_objects(objects)
    return store


@pytest.fixture
def mock_vector_search():
    """Create a mock VectorSearchService."""
    service = MagicMock()
    service.search.return_value = []
    service.search_by_vector.return_value = []
    service.get_vector.return_value = None
    return service


@pytest.fixture
def mock_bm25_index():
    """Create a mock BM25Index."""
    index = MagicMock()
    index.search.return_value = []
    return index


@pytest.fixture
def mock_fusion_retriever():
    """Create a mock FusionRetriever."""
    retriever = MagicMock()
    retriever.hybrid_search.return_value = []
    return retriever


@pytest.fixture
def retrieval_service(sqlite_store, mock_vector_search, mock_bm25_index, mock_fusion_retriever):
    """Create a RetrievalService with real SQLite and mocked search."""
    return RetrievalService(
        vector_search=mock_vector_search,
        fusion_retriever=mock_fusion_retriever,
        bm25_index=mock_bm25_index,
        sqlite_store=sqlite_store,
    )


# =============================================================================
# End-to-End Tests
# =============================================================================


class TestEndToEnd:
    """End-to-end integration tests."""

    def test_e2e_vector_search_with_metadata_enrichment(
        self, retrieval_service, mock_vector_search, sqlite_store
    ) -> None:
        """Full pipeline: vector search → SQLite enrichment → response."""
        # Mock vector search returns 5 results
        mock_vector_search.search.return_value = [
            VectorSearchResult(
                knowledge_id=obj.id,
                score=0.95 - i * 0.01,
                payload={},
            )
            for i, obj in enumerate(sqlite_store.get_all()[:5])
        ]

        response = retrieval_service.search(
            "What's new with GPT-4o?",
            method="vector",
        )

        assert response.query == "What's new with GPT-4o?"
        assert response.total_matches == 5
        assert response.method == "vector"
        assert response.retrieval_time_ms > 0

        # Verify enrichment
        for result in response.results:
            assert result.knowledge_id is not None
            assert result.title is not None
            assert result.source_url is not None
            assert result.content_snippet is not None
            assert result.source_type in ("rss", "github")

    def test_e2e_search_with_metadata_filter(
        self, retrieval_service, mock_vector_search, sqlite_store
    ) -> None:
        """Search with metadata filter applies correctly."""
        all_objects = sqlite_store.get_all()
        rss_objects = [obj for obj in all_objects if obj.source_type == "rss"]

        mock_vector_search.search.return_value = [
            VectorSearchResult(
                knowledge_id=obj.id,
                score=0.9,
                payload={},
            )
            for obj in rss_objects[:3]
        ]

        metadata_filter = MetadataFilter(source_type="rss")
        response = retrieval_service.search(
            "AI research",
            metadata_filter=metadata_filter,
            method="vector",
        )

        assert response.filters_applied is not None
        assert response.filters_applied["source_type"] == "rss"

    def test_e2e_empty_results(self, retrieval_service, mock_vector_search) -> None:
        """Search with no matching results returns empty response."""
        mock_vector_search.search.return_value = []

        response = retrieval_service.search(
            "nonexistent topic xyz",
            method="vector",
        )

        assert response.total_matches == 0
        assert len(response.results) == 0

    def test_e2e_latency_under_200ms(
        self, retrieval_service, mock_vector_search, sqlite_store
    ) -> None:
        """Retrieval latency is under 200ms for 100 items."""
        all_objects = sqlite_store.get_all()
        mock_vector_search.search.return_value = [
            VectorSearchResult(
                knowledge_id=obj.id,
                score=0.9,
                payload={},
            )
            for obj in all_objects[:10]
        ]

        start = time.perf_counter()
        response = retrieval_service.search(
            "GPT-4o AI research",
            method="vector",
        )
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert response.retrieval_time_ms < 200
        assert elapsed_ms < 200

    def test_e2e_json_serialization(
        self, retrieval_service, mock_vector_search, sqlite_store
    ) -> None:
        """Response can be serialized to JSON for MCP-001."""
        import json

        all_objects = sqlite_store.get_all()
        mock_vector_search.search.return_value = [
            VectorSearchResult(
                knowledge_id=all_objects[0].id,
                score=0.95,
                payload={},
            )
        ]

        response = retrieval_service.search(
            "GPT-4o",
            method="vector",
        )

        # Should serialize without errors
        json_str = response.model_dump_json()
        parsed = json.loads(json_str)

        assert "query" in parsed
        assert "results" in parsed
        assert "total_matches" in parsed
        assert "retrieval_time_ms" in parsed

    def test_e2e_all_three_methods(
        self,
        retrieval_service,
        mock_vector_search,
        mock_bm25_index,
        mock_fusion_retriever,
        sqlite_store,
    ) -> None:
        """All three retrieval methods work end-to-end."""
        all_objects = sqlite_store.get_all()

        # Setup mocks
        vector_result = VectorSearchResult(knowledge_id=all_objects[0].id, score=0.9, payload={})
        bm25_result = MagicMock()
        bm25_result.doc_id = all_objects[0].id
        bm25_result.score = 5.0
        fused_result = FusedResult(
            knowledge_id=all_objects[0].id,
            fused_score=0.03,
            vector_score=0.9,
            bm25_score=5.0,
        )

        mock_vector_search.search.return_value = [vector_result]
        mock_bm25_index.search.return_value = [bm25_result]
        mock_fusion_retriever.hybrid_search.return_value = [fused_result]

        # Test each method
        for method in ["vector", "keyword", "hybrid"]:
            response = retrieval_service.search("test", method=method)
            assert response.method == method
            assert response.total_matches >= 0
