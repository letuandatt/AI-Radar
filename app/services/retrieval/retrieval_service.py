"""Unified Retrieval Service.

Provides a single entry point for all retrieval operations,
dispatching to the appropriate strategy (vector, keyword, hybrid).

This is the implementation of the `search_knowledge` tool for MCP-001
and the retrieval API for Web Dashboard (INFRA-002).
"""

import time
from typing import Any

from app.core.logger import get_logger
from app.services.retrieval.filter_models import MetadataFilter
from app.services.retrieval.fusion_retriever import FusedResult, FusionRetriever
from app.services.retrieval.metadata_filter import MetadataFilterEngine
from app.services.retrieval.retrieval_models import (
    InvalidRetrievalMethodError,
    RetrievalMethod,
    RetrievalQueryTooLongError,
    RetrievalResponse,
    RetrievalResult,
    RetrievalServiceUnavailableError,
)
from app.services.retrieval.vector_search import VectorSearchResult, VectorSearchService
from app.storage.knowledge.sqlite_store import SQLiteKnowledgeStore
from app.storage.search.bm25_index import BM25Index, BM25Result

logger = get_logger(__name__)

# Maximum query length
MAX_QUERY_LENGTH = 1000

# Content snippet length
SNIPPET_LENGTH = 300


class RetrievalService:
    """Unified retrieval interface for all search operations.

    Dispatches to the appropriate retrieval strategy based on the
    `method` parameter, enriches results with metadata from SQLite,
    and returns typed responses ready for MCP-001 and Web Dashboard.

    Args:
        vector_search: VectorSearchService for semantic search.
        fusion_retriever: FusionRetriever for hybrid search.
        bm25_index: BM25Index for keyword search.
        sqlite_store: SQLiteKnowledgeStore for metadata enrichment.
        filter_engine: MetadataFilterEngine for filter building.
    """

    def __init__(
        self,
        vector_search: VectorSearchService,
        fusion_retriever: FusionRetriever,
        bm25_index: BM25Index,
        sqlite_store: SQLiteKnowledgeStore,
        filter_engine: MetadataFilterEngine | None = None,
    ) -> None:
        self._vector_search = vector_search
        self._fusion_retriever = fusion_retriever
        self._bm25_index = bm25_index
        self._sqlite_store = sqlite_store
        self._filter_engine = filter_engine or MetadataFilterEngine()

    # ------------------------------------------------------------------
    # Main Search Method
    # ------------------------------------------------------------------

    def search(
        self,
        query: str,
        metadata_filter: MetadataFilter | None = None,
        top_k: int = 10,
        method: str = RetrievalMethod.HYBRID.value,
    ) -> RetrievalResponse:
        """Search the knowledge repository using the specified strategy.

        Args:
            query: Search query text.
            metadata_filter: Optional metadata filter for pre-filtering.
            top_k: Maximum number of results to return.
            method: Retrieval method ("vector", "keyword", "hybrid").

        Returns:
            RetrievalResponse with enriched results.

        Raises:
            RetrievalQueryTooLongError: If query exceeds max length.
            InvalidRetrievalMethodError: If method is invalid.
            RetrievalServiceUnavailableError: If service is unavailable.
        """
        # Validate query
        self._validate_query(query)

        # Validate method
        retrieval_method = self._validate_method(method)

        # Start timing
        start_time = time.perf_counter()

        try:
            # Dispatch to appropriate strategy
            if retrieval_method == RetrievalMethod.VECTOR:
                raw_results = self._search_vector(query, metadata_filter, top_k)
            elif retrieval_method == RetrievalMethod.KEYWORD:
                raw_results = self._search_keyword(query, top_k)  # type: ignore[assignment]
            elif retrieval_method == RetrievalMethod.HYBRID:
                raw_results = self._search_hybrid(query, metadata_filter, top_k)  # type: ignore[assignment]
            else:
                raise InvalidRetrievalMethodError(method)

            # Enrich results with metadata from SQLite
            enriched_results = self._enrich_results(raw_results, retrieval_method)

            # Calculate retrieval time
            elapsed_ms = (time.perf_counter() - start_time) * 1000

            # Build filter description
            filters_applied = None
            if metadata_filter is not None and not metadata_filter.is_empty():
                filters_applied = metadata_filter.model_dump(exclude_none=True)

            response = RetrievalResponse(
                query=query,
                results=enriched_results,
                total_matches=len(enriched_results),
                retrieval_time_ms=round(elapsed_ms, 2),
                filters_applied=filters_applied,
                method=retrieval_method,
            )

            logger.info(
                "Retrieval completed: query='%s', method=%s, results=%d, time=%.1fms",
                query[:50],
                retrieval_method.value,
                len(enriched_results),
                elapsed_ms,
            )

            return response

        except (RetrievalQueryTooLongError, InvalidRetrievalMethodError):
            raise
        except Exception as e:
            logger.error("Retrieval failed: %s", e)
            raise RetrievalServiceUnavailableError(f"Retrieval failed: {e}") from e

    # ------------------------------------------------------------------
    # Related Items ("More Like This")
    # ------------------------------------------------------------------

    def get_related_items(
        self,
        knowledge_id: str,
        top_k: int = 5,
    ) -> RetrievalResponse:
        """Get items related to a specific knowledge object.

        Uses the vector of the specified item to find similar items.

        Args:
            knowledge_id: ID of the knowledge object to find related items for.
            top_k: Maximum number of related items to return.

        Returns:
            RetrievalResponse with related items.

        Raises:
            RetrievalServiceUnavailableError: If item or vector not found.
        """
        start_time = time.perf_counter()

        try:
            # Get the item from SQLite
            item = self._sqlite_store.get_by_id(knowledge_id)
            if item is None:
                raise RetrievalServiceUnavailableError(
                    f"Knowledge object not found: {knowledge_id}"
                )

            # Get the vector from Qdrant
            vector = self._vector_search.get_vector(knowledge_id)
            if vector is None:
                raise RetrievalServiceUnavailableError(
                    f"Vector not found for knowledge object: {knowledge_id}"
                )

            # Search by vector (fetch extra to account for excluding original)
            raw_results = self._vector_search.search_by_vector(
                vector=vector,
                top_k=top_k + 1,
            )

            # Exclude the original item
            filtered_results = [r for r in raw_results if r.knowledge_id != knowledge_id][:top_k]

            # Enrich results
            enriched_results = self._enrich_results(filtered_results, RetrievalMethod.VECTOR.value)

            elapsed_ms = (time.perf_counter() - start_time) * 1000

            response = RetrievalResponse(
                query=f"related_to:{knowledge_id}",
                results=enriched_results,
                total_matches=len(enriched_results),
                retrieval_time_ms=round(elapsed_ms, 2),
                filters_applied=None,
                method=RetrievalMethod.VECTOR.value,
            )

            logger.info(
                "Related items retrieved: knowledge_id=%s, results=%d, time=%.1fms",
                knowledge_id,
                len(enriched_results),
                elapsed_ms,
            )

            return response

        except RetrievalServiceUnavailableError:
            raise
        except Exception as e:
            logger.error("Failed to get related items: %s", e)
            raise RetrievalServiceUnavailableError(f"Failed to get related items: {e}") from e

    # ------------------------------------------------------------------
    # Private: Strategy Dispatch
    # ------------------------------------------------------------------

    def _search_vector(
        self,
        query: str,
        metadata_filter: MetadataFilter | None,
        top_k: int,
    ) -> list[VectorSearchResult]:
        """Execute vector-only search."""
        return self._vector_search.search(
            query=query,
            metadata_filter=metadata_filter,
            top_k=top_k,
        )

    def _search_keyword(
        self,
        query: str,
        top_k: int,
    ) -> list[BM25Result]:
        """Execute keyword-only search (BM25)."""
        return self._bm25_index.search(query=query, top_k=top_k)

    def _search_hybrid(
        self,
        query: str,
        metadata_filter: MetadataFilter | None,
        top_k: int,
    ) -> list[FusedResult]:
        """Execute hybrid search (vector + BM25 fusion)."""
        return self._fusion_retriever.hybrid_search(
            query=query,
            metadata_filter=metadata_filter,
            top_k=top_k,
        )

    # ------------------------------------------------------------------
    # Private: Result Enrichment
    # ------------------------------------------------------------------

    def _enrich_results(
        self,
        raw_results: list[Any],
        retrieval_method: str,
    ) -> list[RetrievalResult]:
        """Enrich raw search results with metadata from SQLite.

        Args:
            raw_results: Raw results from search (VectorSearchResult,
                         BM25Result, or FusedResult).
            retrieval_method: Method used for retrieval.

        Returns:
            List of enriched RetrievalResult objects.
        """
        enriched: list[RetrievalResult] = []

        for result in raw_results:
            # Extract knowledge_id and score based on result type
            knowledge_id, score = self._extract_id_and_score(result)

            if knowledge_id is None:
                continue

            # Get metadata from SQLite
            ko = self._sqlite_store.get_by_id(knowledge_id)
            if ko is None:
                logger.debug(
                    "KnowledgeObject %s not found in SQLite, skipping",
                    knowledge_id,
                )
                continue

            # Build content snippet
            snippet = ko.content_text[:SNIPPET_LENGTH] if ko.content_text else ""

            # Extract topics and entities from metadata
            topics = ko.metadata.topics if ko.metadata else []
            entities = ko.metadata.entities if ko.metadata else []

            enriched.append(
                RetrievalResult(
                    knowledge_id=knowledge_id,
                    title=ko.title,
                    source_url=ko.source_url,
                    content_snippet=snippet,
                    source_type=ko.source_type,
                    source_name=ko.source_name,
                    published_at=ko.published_at,
                    topics=topics,
                    entities=entities,
                    relevance_score=score,
                    retrieval_method=retrieval_method,
                )
            )

        return enriched

    @staticmethod
    def _extract_id_and_score(result: Any) -> tuple[str | None, float]:
        """Extract knowledge_id and score from various result types."""
        if isinstance(result, VectorSearchResult):
            return result.knowledge_id, result.score
        elif isinstance(result, BM25Result):
            return result.doc_id, result.score
        elif isinstance(result, FusedResult):
            return result.knowledge_id, result.fused_score
        else:
            logger.warning("Unknown result type: %s", type(result))
            return None, 0.0

    # ------------------------------------------------------------------
    # Private: Validation
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_query(query: str) -> None:
        """Validate query length."""
        if len(query) > MAX_QUERY_LENGTH:
            raise RetrievalQueryTooLongError(
                query_length=len(query),
                max_length=MAX_QUERY_LENGTH,
            )

    @staticmethod
    def _validate_method(method: str) -> RetrievalMethod:
        """Validate and convert retrieval method string."""
        try:
            return RetrievalMethod(method)
        except ValueError:
            raise InvalidRetrievalMethodError(method) from None
