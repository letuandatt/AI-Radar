"""Fusion Retriever — RAG-001 Hybrid Search.

Combines vector search (Qdrant) and keyword search (BM25)
using Reciprocal Rank Fusion (RRF), with freshness weighting
and content-hash deduplication.
"""

import math
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.core.logger import get_logger
from app.services.retrieval.filter_models import MetadataFilter
from app.services.retrieval.vector_search import VectorSearchResult, VectorSearchService
from app.storage.search.bm25_index import BM25Index, BM25Result

logger = get_logger(__name__)

# Default RRF constant (standard value from literature)
DEFAULT_RRF_K = 60

# Freshness weighting defaults
DEFAULT_DECAY_DAYS = 30
DEFAULT_MAX_BOOST = 0.2


# =============================================================================
# Result Model
# =============================================================================


@dataclass(frozen=True)
class FusedResult:
    """Result from fusion retrieval (RRF).

    Attributes:
        knowledge_id: Knowledge Object ID.
        fused_score: Combined RRF score (with freshness boost).
        vector_score: Original vector similarity score (if available).
        bm25_score: Original BM25 score (if available).
        vector_rank: Rank in vector search results (1-based, if available).
        bm25_rank: Rank in BM25 results (1-based, if available).
        payload: Metadata payload from Qdrant.
        content_hash: Content hash for deduplication.
        published_at: Publication timestamp for freshness weighting.
    """

    knowledge_id: str
    fused_score: float
    vector_score: float | None = None
    bm25_score: float | None = None
    vector_rank: int | None = None
    bm25_rank: int | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    content_hash: str | None = None
    published_at: datetime | None = None


# =============================================================================
# Freshness Weighting
# =============================================================================


def freshness_boost(
    published_at: datetime | None,
    decay_days: int = DEFAULT_DECAY_DAYS,
    max_boost: float = DEFAULT_MAX_BOOST,
    now: datetime | None = None,
) -> float:
    """Calculate freshness boost for a document.

    Recent items get a score boost that decays exponentially
    with age. Items older than decay_days get no boost.

    Args:
        published_at: Publication timestamp of the document.
        decay_days: Number of days for full decay.
        max_boost: Maximum boost factor (e.g., 0.2 = 20%).
        now: Current time (for testing). Defaults to UTC now.

    Returns:
        Boost factor between 0.0 and max_boost.
    """
    if published_at is None:
        return 0.0

    if now is None:
        now = datetime.now(timezone.utc)

    # Ensure both datetimes are timezone-aware
    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    age_days = (now - published_at).total_seconds() / 86400.0

    if age_days <= 0:
        return max_boost

    if age_days >= decay_days:
        return 0.0

    # Exponential decay
    boost = max_boost * math.exp(-age_days / decay_days)
    return boost


# =============================================================================
# Fusion Retriever
# =============================================================================


class FusionRetriever:
    """Hybrid search combining vector search and BM25 via RRF.

    Implements RAG-001 Fusion Retrieval strategy:
    1. Run vector search and BM25 search in parallel.
    2. Fuse results using Reciprocal Rank Fusion (RRF).
    3. Apply freshness weighting.
    4. Deduplicate by content_hash.

    Args:
        vector_search: VectorSearchService instance.
        bm25_index: BM25Index instance.
        rrf_k: RRF constant (default 60).
        decay_days: Freshness decay period in days.
        max_boost: Maximum freshness boost factor.
    """

    def __init__(
        self,
        vector_search: VectorSearchService,
        bm25_index: BM25Index,
        rrf_k: int = DEFAULT_RRF_K,
        decay_days: int = DEFAULT_DECAY_DAYS,
        max_boost: float = DEFAULT_MAX_BOOST,
    ) -> None:
        self._vector_search = vector_search
        self._bm25_index = bm25_index
        self._rrf_k = rrf_k
        self._decay_days = decay_days
        self._max_boost = max_boost

    # ------------------------------------------------------------------
    # RRF Fusion
    # ------------------------------------------------------------------

    def fuse(
        self,
        vector_results: list[VectorSearchResult],
        bm25_results: list[BM25Result],
        k: int | None = None,
    ) -> list[FusedResult]:
        """Fuse vector and BM25 results using Reciprocal Rank Fusion.

        RRF formula:
            score(d) = sum(1 / (k + rank_in_list(d))) for each list

        Args:
            vector_results: Results from vector search.
            bm25_results: Results from BM25 search.
            k: RRF constant. Defaults to self._rrf_k.

        Returns:
            List of FusedResult sorted by fused_score descending.
        """
        if k is None:
            k = self._rrf_k

        # Build lookup maps
        fused_scores: dict[str, float] = {}
        vector_info: dict[str, tuple[float, int, dict]] = {}
        bm25_info: dict[str, tuple[float, int]] = {}

        # Process vector results
        for rank, result in enumerate(vector_results, start=1):
            kid = result.knowledge_id
            rrf_contribution = 1.0 / (k + rank)
            fused_scores[kid] = fused_scores.get(kid, 0.0) + rrf_contribution
            vector_info[kid] = (result.score, rank, result.payload)

        # Process BM25 results
        for rank, result in enumerate(bm25_results, start=1):  # type: ignore[assignment]
            kid = result.doc_id  # type: ignore[attr-defined]
            rrf_contribution = 1.0 / (k + rank)
            fused_scores[kid] = fused_scores.get(kid, 0.0) + rrf_contribution
            bm25_info[kid] = (result.score, rank)

        # Build FusedResult list
        results: list[FusedResult] = []
        for kid, score in fused_scores.items():
            v_info = vector_info.get(kid)
            b_info = bm25_info.get(kid)

            payload = v_info[2] if v_info else {}

            results.append(
                FusedResult(
                    knowledge_id=kid,
                    fused_score=score,
                    vector_score=v_info[0] if v_info else None,
                    bm25_score=b_info[0] if b_info else None,
                    vector_rank=v_info[1] if v_info else None,
                    bm25_rank=b_info[1] if b_info else None,
                    payload=payload,
                    content_hash=payload.get("content_hash"),
                    published_at=self._parse_published_at(payload.get("published_at")),
                )
            )

        # Sort by fused score descending
        results.sort(key=lambda r: r.fused_score, reverse=True)

        logger.debug(
            "RRF fusion: %d vector + %d bm25 → %d fused results",
            len(vector_results),
            len(bm25_results),
            len(results),
        )

        return results

    # ------------------------------------------------------------------
    # Hybrid Search
    # ------------------------------------------------------------------

    def hybrid_search(
        self,
        query: str,
        metadata_filter: MetadataFilter | None = None,
        top_k: int = 10,
        fetch_k: int | None = None,
    ) -> list[FusedResult]:
        """Run hybrid search: vector + BM25 in parallel, then fuse.

        Steps:
        1. Run vector search and BM25 search in parallel.
        2. Fuse results using RRF.
        3. Apply freshness weighting.
        4. Deduplicate by content_hash.
        5. Return top_k results.

        Args:
            query: Search query text.
            metadata_filter: Optional metadata filter.
            top_k: Number of final results to return.
            fetch_k: Number of results to fetch from each source.
                     Defaults to top_k * 3 for better fusion quality.

        Returns:
            List of FusedResult sorted by final score descending.
        """
        if fetch_k is None:
            fetch_k = top_k * 3

        start_time = time.perf_counter()

        # Step 1: Run searches in parallel using ThreadPoolExecutor
        vector_results, bm25_results = self._parallel_search(
            query=query,
            metadata_filter=metadata_filter,
            fetch_k=fetch_k,
        )

        # Step 2: Fuse with RRF
        fused = self.fuse(vector_results, bm25_results)

        # Step 3: Apply freshness weighting
        boosted = self._apply_freshness_weighting(fused)

        # Step 4: Deduplicate by content_hash
        deduped = self._deduplicate_by_content_hash(boosted)

        # Step 5: Return top_k
        final = deduped[:top_k]

        elapsed_ms = (time.perf_counter() - start_time) * 1000
        logger.info(
            "Hybrid search completed: query='%s', "
            "vector=%d, bm25=%d, fused=%d, deduped=%d, final=%d, "
            "elapsed=%.1fms",
            query[:50],
            len(vector_results),
            len(bm25_results),
            len(fused),
            len(deduped),
            len(final),
            elapsed_ms,
        )

        return final

    # ------------------------------------------------------------------
    # Private: Parallel Search
    # ------------------------------------------------------------------

    def _parallel_search(
        self,
        query: str,
        metadata_filter: MetadataFilter | None,
        fetch_k: int,
    ) -> tuple[list[VectorSearchResult], list[BM25Result]]:
        """Run vector and BM25 searches in parallel."""
        vector_results: list[VectorSearchResult] = []
        bm25_results: list[BM25Result] = []

        with ThreadPoolExecutor(max_workers=2) as executor:
            vector_future = executor.submit(
                self._vector_search.search,
                query,
                metadata_filter,
                fetch_k,
            )
            bm25_future = executor.submit(
                self._bm25_index.search,
                query,
                fetch_k,
            )

            # Collect results, handling errors gracefully
            try:
                vector_results = vector_future.result(timeout=30.0)
            except Exception as e:
                logger.error("Vector search failed: %s", e)

            try:
                bm25_results = bm25_future.result(timeout=30.0)
            except Exception as e:
                logger.error("BM25 search failed: %s", e)

        return vector_results, bm25_results

    # ------------------------------------------------------------------
    # Private: Freshness Weighting
    # ------------------------------------------------------------------

    def _apply_freshness_weighting(self, results: list[FusedResult]) -> list[FusedResult]:
        """Apply freshness boost to fused scores."""
        boosted: list[FusedResult] = []

        for result in results:
            boost = freshness_boost(
                published_at=result.published_at,
                decay_days=self._decay_days,
                max_boost=self._max_boost,
            )

            new_score = result.fused_score * (1.0 + boost)

            boosted.append(
                FusedResult(
                    knowledge_id=result.knowledge_id,
                    fused_score=new_score,
                    vector_score=result.vector_score,
                    bm25_score=result.bm25_score,
                    vector_rank=result.vector_rank,
                    bm25_rank=result.bm25_rank,
                    payload=result.payload,
                    content_hash=result.content_hash,
                    published_at=result.published_at,
                )
            )

        # Re-sort after boosting
        boosted.sort(key=lambda r: r.fused_score, reverse=True)
        return boosted

    # ------------------------------------------------------------------
    # Private: Deduplication (DATA-001)
    # ------------------------------------------------------------------

    def _deduplicate_by_content_hash(self, results: list[FusedResult]) -> list[FusedResult]:
        """Remove duplicates by content_hash, keeping highest score."""
        seen_hashes: dict[str, FusedResult] = {}
        no_hash: list[FusedResult] = []

        for result in results:
            if result.content_hash is None:
                no_hash.append(result)
                continue

            if result.content_hash not in seen_hashes:
                seen_hashes[result.content_hash] = result
            else:
                existing = seen_hashes[result.content_hash]
                if result.fused_score > existing.fused_score:
                    seen_hashes[result.content_hash] = result

        deduped = list(seen_hashes.values()) + no_hash
        deduped.sort(key=lambda r: r.fused_score, reverse=True)

        removed = len(results) - len(deduped)
        if removed > 0:
            logger.debug("Deduplication removed %d duplicate results", removed)

        return deduped

    # ------------------------------------------------------------------
    # Private: Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_published_at(value: Any) -> datetime | None:
        """Parse published_at from payload (ISO string or datetime)."""
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value)
            except (ValueError, TypeError):
                return None
        return None
