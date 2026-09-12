"""Vector Search Service.

Provides semantic search over the Qdrant vector store
with optional metadata pre-filtering.

Part of RAG-001 Retrieval Strategy implementation.
"""

from dataclasses import dataclass, field
from typing import Any

from app.core.logger import get_logger
from app.services.embedding.provider import EmbeddingProvider
from app.services.retrieval.filter_models import MetadataFilter
from app.services.retrieval.metadata_filter import MetadataFilterEngine
from app.storage.vector.qdrant_store import QdrantVectorStore

logger = get_logger(__name__)


# =============================================================================
# Result Model
# =============================================================================


@dataclass(frozen=True)
class VectorSearchResult:
    """Result from vector similarity search.

    Attributes:
        knowledge_id: Knowledge Object ID (used as Qdrant point ID).
        score: Cosine similarity score from Qdrant.
        payload: Qdrant payload with metadata.
    """

    knowledge_id: str
    score: float
    payload: dict[str, Any] = field(default_factory=dict)


# =============================================================================
# Vector Search Service
# =============================================================================


class VectorSearchService:
    """Semantic search service using Qdrant vector store.

    Embeds query text and searches for nearest neighbors
    with optional metadata pre-filtering.

    Args:
        qdrant_store: QdrantVectorStore instance.
        embedding_provider: EmbeddingProvider for query embedding.
        filter_engine: MetadataFilterEngine for filter conversion.
    """

    def __init__(
        self,
        qdrant_store: QdrantVectorStore,
        embedding_provider: EmbeddingProvider,
        filter_engine: MetadataFilterEngine | None = None,
    ) -> None:
        self._qdrant_store = qdrant_store
        self._embedding_provider = embedding_provider
        self._filter_engine = filter_engine or MetadataFilterEngine()

    # ------------------------------------------------------------------
    # Search Methods
    # ------------------------------------------------------------------

    def search(
        self,
        query: str,
        metadata_filter: MetadataFilter | None = None,
        top_k: int = 20,
    ) -> list[VectorSearchResult]:
        """Search for semantically similar knowledge objects.

        Steps:
        1. Build Qdrant filter from MetadataFilter (pre-filtering).
        2. Embed query text.
        3. Search Qdrant with filter +vector.

        Args:
            query: Search query text.
            metadata_filter: Optional metadata filter for pre-filtering.
            top_k: Maximum number of results.

        Returns:
            List of VectorSearchResult sorted by score descending.
        """
        # Step 1: Build Qdrant filter
        qdrant_filter = None
        if metadata_filter is not None and not metadata_filter.is_empty():
            qdrant_filter = self._filter_engine.build_qdrant_filter(metadata_filter)

        # Step 2: Embed query
        query_vector = self._embedding_provider.embed_text(query)

        # Step 3: Search Qdrant
        return self.search_by_vector(
            vector=query_vector,
            metadata_filter=metadata_filter,
            top_k=top_k,
            _prebuilt_filter=qdrant_filter,
        )

    def search_by_vector(
        self,
        vector: list[float],
        metadata_filter: MetadataFilter | None = None,
        top_k: int = 20,
        _prebuilt_filter: Any = None,
    ) -> list[VectorSearchResult]:
        """Search using a pre-computed vector.

        Useful for "more like this" queries where the vector
        is already available.

        Args:
            vector: Pre-computed embedding vector.
            metadata_filter: Optional metadata filter.
            top_k: Maximum number of results.
            _prebuilt_filter: Internal use — pre-built Qdrant filter.

        Returns:
            List of VectorSearchResult sorted by score descending.
        """
        # Build filter if not pre-built
        qdrant_filter = _prebuilt_filter
        if qdrant_filter is None and metadata_filter is not None:
            if not metadata_filter.is_empty():
                qdrant_filter = self._filter_engine.build_qdrant_filter(metadata_filter)

        # Search Qdrant
        raw_results = self._qdrant_store.search_vectors(
            query_vector=vector,
            query_filter=qdrant_filter,
            limit=top_k,
            with_payload=True,
        )

        # Convert to VectorSearchResult
        results = [
            VectorSearchResult(
                knowledge_id=r["id"],
                score=r["score"],
                payload=r["payload"],
            )
            for r in raw_results
        ]

        logger.debug(
            "Vector search returned %d results (top_k=%d)",
            len(results),
            top_k,
        )

        return results

    # ------------------------------------------------------------------
    # Vector Retrieval
    # ------------------------------------------------------------------

    def get_vector(self, knowledge_id: str) -> list[float] | None:
        """Retrieve the embedding vector for a knowledge object.

        Args:
            knowledge_id: Knowledge Object ID.

        Returns:
            Embedding vector, or None if not found.
        """
        point = self._qdrant_store.get_point(knowledge_id)
        if point is None:
            return None
        return point.vector
