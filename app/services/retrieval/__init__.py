"""Retrieval services package."""

from app.services.retrieval.filter_models import (
    FilterCombination,
    FilterSeverity,
    FilterValidationError,
    MetadataFilter,
)
from app.services.retrieval.fusion_retriever import (
    DEFAULT_RRF_K,
    FusedResult,
    FusionRetriever,
    freshness_boost,
)
from app.services.retrieval.metadata_filter import MetadataFilterEngine
from app.services.retrieval.vector_search import (
    VectorSearchResult,
    VectorSearchService,
)

__all__ = [
    # Filter models
    "MetadataFilter",
    "FilterCombination",
    "FilterValidationError",
    "FilterSeverity",
    # Filter engine
    "MetadataFilterEngine",
    # Vector search
    "VectorSearchService",
    "VectorSearchResult",
    # Fusion retriever
    "FusionRetriever",
    "FusedResult",
    "freshness_boost",
    "DEFAULT_RRF_K",
]
