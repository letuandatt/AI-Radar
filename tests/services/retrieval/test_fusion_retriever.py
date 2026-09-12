"""Unit tests for FusionRetriever."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from app.services.retrieval.fusion_retriever import (
    DEFAULT_RRF_K,
    FusedResult,
    FusionRetriever,
    freshness_boost,
)
from app.services.retrieval.vector_search import VectorSearchResult
from app.storage.search.bm25_index import BM25Result

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_vector_search():
    """Create a mock VectorSearchService."""
    service = MagicMock()
    service.search.return_value = []
    return service


@pytest.fixture
def mock_bm25_index():
    """Create a mock BM25Index."""
    index = MagicMock()
    index.search.return_value = []
    return index


@pytest.fixture
def retriever(mock_vector_search, mock_bm25_index):
    """Create a FusionRetriever with mocks."""
    return FusionRetriever(
        vector_search=mock_vector_search,
        bm25_index=mock_bm25_index,
    )


def _make_vector_result(
    knowledge_id: str,
    score: float = 0.9,
    payload: dict | None = None,
) -> VectorSearchResult:
    """Helper to create a VectorSearchResult."""
    return VectorSearchResult(
        knowledge_id=knowledge_id,
        score=score,
        payload=payload or {},
    )


def _make_bm25_result(
    doc_id: str,
    score: float = 5.0,
) -> BM25Result:
    """Helper to create a BM25Result."""
    return BM25Result(doc_id=doc_id, score=score)


# =============================================================================
# RRF Fusion Tests
# =============================================================================


class TestRRFFusion:
    """Tests for Reciprocal Rank Fusion."""

    def test_fuse_empty_lists(self, retriever) -> None:
        """Fusing empty lists returns empty result."""
        results = retriever.fuse([], [])
        assert results == []

    def test_fuse_vector_only(self, retriever) -> None:
        """Fusing with only vector results works."""
        vector_results = [
            _make_vector_result("A", 0.9),
            _make_vector_result("B", 0.8),
        ]
        results = retriever.fuse(vector_results, [])

        assert len(results) == 2
        assert results[0].knowledge_id == "A"
        assert results[1].knowledge_id == "B"

    def test_fuse_bm25_only(self, retriever) -> None:
        """Fusing with only BM25 results works."""
        bm25_results = [
            _make_bm25_result("A", 5.0),
            _make_bm25_result("B", 3.0),
        ]
        results = retriever.fuse([], bm25_results)

        assert len(results) == 2
        assert results[0].knowledge_id == "A"
        assert results[1].knowledge_id == "B"

    def test_fuse_rrf_formula(self, retriever) -> None:
        """RRF formula: score(d) = sum(1/(k+rank)) for each list."""
        k = DEFAULT_RRF_K  # 60

        vector_results = [
            _make_vector_result("A", 0.9),  # rank 1 in vector
            _make_vector_result("B", 0.8),  # rank 2 in vector
        ]
        bm25_results = [
            _make_bm25_result("B", 5.0),  # rank 1 in bm25
            _make_bm25_result("C", 3.0),  # rank 2 in bm25
        ]

        results = retriever.fuse(vector_results, bm25_results)

        # Expected scores:
        # A: 1/(60+1) = 0.016393 (vector rank 1 only)
        # B: 1/(60+2) + 1/(60+1) = 0.016129 + 0.016393 = 0.032522
        # C: 1/(60+2) = 0.016129 (bm25 rank 2 only)

        result_map = {r.knowledge_id: r for r in results}

        expected_a = 1.0 / (k + 1)
        expected_b = 1.0 / (k + 2) + 1.0 / (k + 1)
        expected_c = 1.0 / (k + 2)

        assert abs(result_map["A"].fused_score - expected_a) < 1e-6
        assert abs(result_map["B"].fused_score - expected_b) < 1e-6
        assert abs(result_map["C"].fused_score - expected_c) < 1e-6

    def test_fuse_common_items_rank_higher(self, retriever) -> None:
        """Items in both lists rank higher than items in one list."""
        vector_results = [
            _make_vector_result("A", 0.9),
            _make_vector_result("B", 0.8),
            _make_vector_result("C", 0.7),
        ]
        bm25_results = [
            _make_bm25_result("B", 5.0),
            _make_bm25_result("C", 3.0),
            _make_bm25_result("D", 2.0),
        ]

        results = retriever.fuse(vector_results, bm25_results)

        # B and C appear in both lists → higher RRF scores
        result_ids = [r.knowledge_id for r in results]

        # B is in vector (rank 2) + bm25 (rank 1) → highest
        # C is in vector (rank 3) + bm25 (rank 2) → second
        assert result_ids[0] == "B"
        assert result_ids[1] == "C"

    def test_fuse_preserves_metadata(self, retriever) -> None:
        """Fused results preserve vector scores, ranks, and payload."""
        vector_results = [
            _make_vector_result("A", 0.95, {"title": "Test"}),
        ]
        bm25_results = [
            _make_bm25_result("A", 5.0),
        ]

        results = retriever.fuse(vector_results, bm25_results)

        assert len(results) == 1
        result = results[0]
        assert result.knowledge_id == "A"
        assert result.vector_score == 0.95
        assert result.bm25_score == 5.0
        assert result.vector_rank == 1
        assert result.bm25_rank == 1
        assert result.payload["title"] == "Test"

    def test_fuse_custom_k(self, retriever) -> None:
        """Fusing with custom k parameter works."""
        vector_results = [_make_vector_result("A", 0.9)]

        results_default = retriever.fuse(vector_results, [])
        results_custom = retriever.fuse(vector_results, [], k=10)

        # With k=10: score = 1/(10+1) = 0.0909
        # With k=60: score = 1/(60+1) = 0.0164
        assert results_custom[0].fused_score > results_default[0].fused_score


# =============================================================================
# Freshness Weighting Tests
# =============================================================================


class TestFreshnessWeighting:
    """Tests for freshness_boost function."""

    def test_recent_item_gets_max_boost(self) -> None:
        """Item published today gets maximum boost."""
        now = datetime.now(timezone.utc)
        boost = freshness_boost(published_at=now, now=now)
        assert abs(boost - 0.2) < 0.01

    def test_old_item_gets_no_boost(self) -> None:
        """Item older than decay_days gets no boost."""
        now = datetime.now(timezone.utc)
        old = now - timedelta(days=60)
        boost = freshness_boost(published_at=old, now=now)
        assert boost == 0.0

    def test_intermediate_age_gets_partial_boost(self) -> None:
        """Item with intermediate age gets partial boost."""
        now = datetime.now(timezone.utc)
        intermediate = now - timedelta(days=15)
        boost = freshness_boost(published_at=intermediate, now=now)
        assert 0.0 < boost < 0.2

    def test_none_published_at_gets_no_boost(self) -> None:
        """Item without published_at gets no boost."""
        boost = freshness_boost(published_at=None)
        assert boost == 0.0

    def test_boost_decreases_with_age(self) -> None:
        """Boost decreases monotonically with age."""
        now = datetime.now(timezone.utc)

        boosts = []
        for days in [0, 5, 10, 15, 20, 25, 30]:
            published = now - timedelta(days=days)
            boost = freshness_boost(published_at=published, now=now)
            boosts.append(boost)

        # Verify monotonically decreasing
        for i in range(len(boosts) - 1):
            assert boosts[i] >= boosts[i + 1]

    def test_recent_item_ranks_higher_in_hybrid(self, retriever) -> None:
        """Two items with same RRF score: recent ranks higher."""
        now = datetime.now(timezone.utc)

        # Both items have same RRF score (only in vector list, same rank)
        vector_results = [
            _make_vector_result(
                "old_item",
                0.9,
                {"published_at": (now - timedelta(days=60)).isoformat()},
            ),
            _make_vector_result(
                "new_item",
                0.9,
                {"published_at": now.isoformat()},
            ),
        ]

        # Fuse and apply freshness
        fused = retriever.fuse(vector_results, [])
        boosted = retriever._apply_freshness_weighting(fused)

        # new_item should rank higher due to freshness boost
        assert boosted[0].knowledge_id == "new_item"
        assert boosted[1].knowledge_id == "old_item"


# =============================================================================
# Deduplication Tests (DATA-001)
# =============================================================================


class TestDeduplication:
    """Tests for content_hash deduplication."""

    def test_dedup_removes_duplicates(self, retriever) -> None:
        """Items with same content_hash are deduplicated."""
        results = [
            FusedResult(
                knowledge_id="ko_1",
                fused_score=0.9,
                content_hash="hash_A",
            ),
            FusedResult(
                knowledge_id="ko_2",
                fused_score=0.8,
                content_hash="hash_A",  # Duplicate!
            ),
            FusedResult(
                knowledge_id="ko_3",
                fused_score=0.7,
                content_hash="hash_B",
            ),
        ]

        deduped = retriever._deduplicate_by_content_hash(results)

        assert len(deduped) == 2
        ids = {r.knowledge_id for r in deduped}
        assert "ko_1" in ids  # Higher score kept
        assert "ko_3" in ids
        assert "ko_2" not in ids  # Duplicate removed

    def test_dedup_keeps_highest_score(self, retriever) -> None:
        """Deduplication keeps the item with highest fused score."""
        results = [
            FusedResult(
                knowledge_id="ko_1",
                fused_score=0.5,
                content_hash="hash_A",
            ),
            FusedResult(
                knowledge_id="ko_2",
                fused_score=0.9,
                content_hash="hash_A",  # Duplicate with higher score
            ),
        ]

        deduped = retriever._deduplicate_by_content_hash(results)

        assert len(deduped) == 1
        assert deduped[0].knowledge_id == "ko_2"
        assert deduped[0].fused_score == 0.9

    def test_dedup_preserves_items_without_hash(self, retriever) -> None:
        """Items without content_hash are preserved."""
        results = [
            FusedResult(
                knowledge_id="ko_1",
                fused_score=0.9,
                content_hash=None,
            ),
            FusedResult(
                knowledge_id="ko_2",
                fused_score=0.8,
                content_hash=None,
            ),
        ]

        deduped = retriever._deduplicate_by_content_hash(results)
        assert len(deduped) == 2


# =============================================================================
# Hybrid Search Tests
# =============================================================================


class TestHybridSearch:
    """Tests for hybrid_search method."""

    def test_hybrid_search_calls_both_sources(
        self, retriever, mock_vector_search, mock_bm25_index
    ) -> None:
        """hybrid_search() calls both vector and BM25 search."""
        retriever.hybrid_search("test query")

        mock_vector_search.search.assert_called_once()
        mock_bm25_index.search.assert_called_once()

    def test_hybrid_search_returns_fused_results(
        self, retriever, mock_vector_search, mock_bm25_index
    ) -> None:
        """hybrid_search() returns FusedResult list."""
        mock_vector_search.search.return_value = [
            _make_vector_result("A", 0.9, {"content_hash": "h1"}),
        ]
        mock_bm25_index.search.return_value = [
            _make_bm25_result("A", 5.0),
        ]

        results = retriever.hybrid_search("test query")

        assert len(results) == 1
        assert isinstance(results[0], FusedResult)
        assert results[0].knowledge_id == "A"

    def test_hybrid_search_respects_top_k(
        self, retriever, mock_vector_search, mock_bm25_index
    ) -> None:
        """hybrid_search() returns at most top_k results."""
        mock_vector_search.search.return_value = [
            _make_vector_result(f"v_{i}", 0.9 - i * 0.01) for i in range(10)
        ]
        mock_bm25_index.search.return_value = [
            _make_bm25_result(f"b_{i}", 5.0 - i * 0.1) for i in range(10)
        ]

        results = retriever.hybrid_search("test query", top_k=5)

        assert len(results) <= 5

    def test_hybrid_search_handles_vector_failure(
        self, retriever, mock_vector_search, mock_bm25_index
    ) -> None:
        """hybrid_search() continues if vector search fails."""
        mock_vector_search.search.side_effect = Exception("Qdrant down")
        mock_bm25_index.search.return_value = [
            _make_bm25_result("A", 5.0),
        ]

        results = retriever.hybrid_search("test query")

        # Should still return BM25 results
        assert len(results) >= 1

    def test_hybrid_search_handles_bm25_failure(
        self, retriever, mock_vector_search, mock_bm25_index
    ) -> None:
        """hybrid_search() continues if BM25 search fails."""
        mock_vector_search.search.return_value = [
            _make_vector_result("A", 0.9),
        ]
        mock_bm25_index.search.side_effect = Exception("BM25 error")

        results = retriever.hybrid_search("test query")

        # Should still return vector results
        assert len(results) >= 1

    def test_hybrid_search_handles_both_failures(
        self, retriever, mock_vector_search, mock_bm25_index
    ) -> None:
        """hybrid_search() returns empty list if both sources fail."""
        mock_vector_search.search.side_effect = Exception("Qdrant down")
        mock_bm25_index.search.side_effect = Exception("BM25 error")

        results = retriever.hybrid_search("test query")

        assert results == []
