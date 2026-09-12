"""Unit tests for VectorIndexConfig and Qdrant index configuration."""

from dataclasses import FrozenInstanceError
from unittest.mock import MagicMock, patch

import pytest
from qdrant_client.http import models as qdrant_models

from app.storage.vector.index_config import (
    DEFAULT_PAYLOAD_INDEX_FIELDS,
    VectorIndexConfig,
)
from app.storage.vector.qdrant_store import QdrantVectorStore, VectorStoreError


@pytest.fixture
def mock_qdrant_client():
    """Create a mock QdrantClient."""
    with patch("app.storage.vector.qdrant_store.QdrantClient") as mock_class:
        mock_client = MagicMock()
        mock_class.return_value = mock_client
        yield mock_client


# =============================================================================
# VectorIndexConfig Tests
# =============================================================================


class TestVectorIndexConfig:
    """Tests for VectorIndexConfig."""

    def test_defaults_keep_qdrant_defaults(self) -> None:
        """Default config uses None for HNSW params."""
        config = VectorIndexConfig()

        assert config.hnsw_m is None
        assert config.hnsw_ef_construct is None
        assert config.hnsw_ef is None
        assert config.quantization_config is None
        assert config.payload_index_fields == DEFAULT_PAYLOAD_INDEX_FIELDS

    def test_build_hnsw_collection_params_empty_by_default(self) -> None:
        """Default config produces no HNSW collection params."""
        config = VectorIndexConfig()
        assert config.build_hnsw_collection_params() == {}

    def test_build_hnsw_collection_params_partial(self) -> None:
        """Only configured HNSW params are included."""
        config = VectorIndexConfig(hnsw_m=32)
        params = config.build_hnsw_collection_params()

        assert params == {"m": 32}

    def test_build_hnsw_collection_params_full(self) -> None:
        """Full HNSW collection params are included."""
        config = VectorIndexConfig(hnsw_m=32, hnsw_ef_construct=128)
        params = config.build_hnsw_collection_params()

        assert params == {"m": 32, "ef_construct": 128}

    def test_build_search_params_empty_by_default(self) -> None:
        """Default config produces no search params."""
        config = VectorIndexConfig()
        assert config.build_search_params() == {}

    def test_build_search_params_with_ef(self) -> None:
        """Search params include ef when configured."""
        config = VectorIndexConfig(hnsw_ef=256)
        assert config.build_search_params() == {"ef": 256}

    def test_config_is_frozen(self) -> None:
        """VectorIndexConfig is immutable."""
        config = VectorIndexConfig()

        with pytest.raises(FrozenInstanceError):
            config.hnsw_m = 32  # type: ignore[misc]


# =============================================================================
# Qdrant HNSW Configuration Tests
# =============================================================================


class TestQdrantHnswConfiguration:
    """Tests for HNSW configuration in QdrantVectorStore."""

    def test_create_collection_default_keeps_qdrant_defaults(
        self, mock_qdrant_client: MagicMock
    ) -> None:
        """Default config does not pass HNSW overrides."""
        store = QdrantVectorStore(dimensions=8)
        store.create_collection()

        kwargs = mock_qdrant_client.create_collection.call_args.kwargs

        assert kwargs["collection_name"] == "knowledge_objects"
        assert "hnsw_config" not in kwargs
        assert "quantization_config" not in kwargs

    def test_create_collection_with_custom_hnsw(self, mock_qdrant_client: MagicMock) -> None:
        """Custom HNSW config is passed to Qdrant."""
        config = VectorIndexConfig(hnsw_m=32, hnsw_ef_construct=128)
        store = QdrantVectorStore(dimensions=8, index_config=config)

        store.create_collection()

        kwargs = mock_qdrant_client.create_collection.call_args.kwargs
        hnsw = kwargs["hnsw_config"]

        assert hnsw.m == 32
        assert hnsw.ef_construct == 128

    def test_create_collection_requires_dimensions(self, mock_qdrant_client: MagicMock) -> None:
        """create_collection raises if dimensions are missing."""
        store = QdrantVectorStore(dimensions=None)

        with pytest.raises(VectorStoreError, match="dimensions"):
            store.create_collection()


# =============================================================================
# Payload Index Tests
# =============================================================================


class TestPayloadIndexes:
    """Tests for Qdrant payload index creation."""

    def test_ensure_payload_indexes_default_fields(self, mock_qdrant_client: MagicMock) -> None:
        """Default payload indexes are created for filterable fields."""
        store = QdrantVectorStore(dimensions=8)

        created = store.ensure_payload_indexes()

        assert created == len(DEFAULT_PAYLOAD_INDEX_FIELDS)
        assert mock_qdrant_client.create_payload_index.call_count == len(
            DEFAULT_PAYLOAD_INDEX_FIELDS
        )

        calls = {
            call.kwargs["field_name"]: call.kwargs["field_schema"]
            for call in mock_qdrant_client.create_payload_index.call_args_list
        }

        assert calls["source_type"] == qdrant_models.PayloadSchemaType.KEYWORD
        assert calls["source_name"] == qdrant_models.PayloadSchemaType.KEYWORD
        assert calls["published_at"] == qdrant_models.PayloadSchemaType.DATETIME
        assert calls["topics"] == qdrant_models.PayloadSchemaType.KEYWORD

    def test_ensure_payload_indexes_custom_fields(self, mock_qdrant_client: MagicMock) -> None:
        """Custom payload index fields are respected."""
        config = VectorIndexConfig(payload_index_fields=("source_type",))
        store = QdrantVectorStore(dimensions=8, index_config=config)

        created = store.ensure_payload_indexes()

        assert created == 1
        mock_qdrant_client.create_payload_index.assert_called_once()

    def test_ensure_collection_creates_payload_indexes(self, mock_qdrant_client: MagicMock) -> None:
        """ensure_collection creates collection and payload indexes."""
        mock_qdrant_client.get_collections.return_value.collections = []

        store = QdrantVectorStore(dimensions=8)
        store.ensure_collection()

        mock_qdrant_client.create_collection.assert_called_once()
        assert mock_qdrant_client.create_payload_index.call_count == len(
            DEFAULT_PAYLOAD_INDEX_FIELDS
        )


# =============================================================================
# Optimizer Tests
# =============================================================================


class TestOptimizeIndex:
    """Tests for optimize_index method."""

    def test_optimize_index_calls_update_collection(self, mock_qdrant_client: MagicMock) -> None:
        """optimize_index triggers Qdrant optimizer."""
        info = MagicMock()
        info.status = "green"
        info.points_count = 100
        info.indexed_vectors_count = 95
        info.optimizer_status = None

        mock_qdrant_client.get_collection.return_value = info

        store = QdrantVectorStore(dimensions=8)
        result = store.optimize_index()

        mock_qdrant_client.update_collection.assert_called_once()

        kwargs = mock_qdrant_client.update_collection.call_args.kwargs
        assert kwargs["collection_name"] == "knowledge_objects"
        assert kwargs["optimizer_config"].indexing_threshold == 0

        assert result["collection"] == "knowledge_objects"
        assert result["status"] == "green"
        assert result["points_count"] == 100
        assert result["indexed_vectors_count"] == 95
        assert result["estimated_completion_time"] is None

    def test_optimize_index_error(self, mock_qdrant_client: MagicMock) -> None:
        """optimize_index raises VectorStoreError on failure."""
        mock_qdrant_client.update_collection.side_effect = Exception("down")

        store = QdrantVectorStore(dimensions=8)

        with pytest.raises(VectorStoreError, match="Failed to optimize index"):
            store.optimize_index()
