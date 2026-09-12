"""Vector index configuration for Qdrant.

This module centralizes tunable vector index parameters.
Default values are intentionally None to keep Qdrant defaults.
"""

from dataclasses import dataclass
from typing import Any

DEFAULT_PAYLOAD_INDEX_FIELDS: tuple[str, ...] = (
    "source_type",
    "source_name",
    "published_at",
    "topics",
)


@dataclass(frozen=True)
class VectorIndexConfig:
    """Configuration for Qdrant vector indexing.

    Attributes:
        hnsw_m: HNSW connections per element. None keeps Qdrant default.
        hnsw_ef_construct: HNSW indexing-time candidate list size.
        hnsw_ef: HNSW search-time candidate list size.
        quantization_config: Optional Qdrant quantization config object.
        payload_index_fields: Payload fields to index for filtering.
    """

    hnsw_m: int | None = None
    hnsw_ef_construct: int | None = None
    hnsw_ef: int | None = None
    quantization_config: Any | None = None
    payload_index_fields: tuple[str, ...] = DEFAULT_PAYLOAD_INDEX_FIELDS

    def build_hnsw_collection_params(self) -> dict[str, int]:
        """Build HNSW params for collection creation.

        Only includes values explicitly configured. Empty dict means
        Qdrant defaults should be used.

        Returns:
            Dict with optional keys: m, ef_construct.
        """
        params: dict[str, int] = {}

        if self.hnsw_m is not None:
            params["m"] = self.hnsw_m

        if self.hnsw_ef_construct is not None:
            params["ef_construct"] = self.hnsw_ef_construct

        return params

    def build_search_params(self) -> dict[str, int]:
        """Build HNSW search-time params.

        This will be consumed by retrieval services in Sprint 18.

        Returns:
            Dict with optional key: ef.
        """
        params: dict[str, int] = {}

        if self.hnsw_ef is not None:
            params["ef"] = self.hnsw_ef

        return params
