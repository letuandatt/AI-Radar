"""Unit tests for CohereEmbeddingProvider."""

from unittest.mock import MagicMock, patch

import pytest

from app.services.embedding.cohere_provider import (
    CohereEmbeddingProvider,
    EmbeddingError,
)
from app.storage.knowledge.base import CircuitBreaker


@pytest.fixture
def provider() -> CohereEmbeddingProvider:
    return CohereEmbeddingProvider(api_key="test-key")


class TestCohereEmbedText:
    """Tests for embed_text method."""

    @patch("cohere.Client")
    def test_embed_text_success(self, mock_client_class: MagicMock) -> None:
        """Successful embedding returns vector."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.embeddings = [[0.1] * 1024]
        mock_client.embed.return_value = mock_response
        mock_client_class.return_value = mock_client

        provider = CohereEmbeddingProvider(api_key="test-key")
        vector = provider.embed_text("Test text")

        assert len(vector) == 1024
        assert all(isinstance(x, float) for x in vector)

    @patch("cohere.Client")
    def test_embed_text_circuit_open(self, mock_client_class: MagicMock) -> None:
        """Circuit breaker open raises EmbeddingError."""
        cb = CircuitBreaker(failure_threshold=1)
        cb.record_failure()

        provider = CohereEmbeddingProvider(api_key="test-key", circuit_breaker=cb)

        with pytest.raises(EmbeddingError, match="Circuit breaker"):
            provider.embed_text("Test text")


class TestCohereEmbedBatch:
    """Tests for embed_batch method."""

    @patch("cohere.Client")
    def test_embed_batch_success(self, mock_client_class: MagicMock) -> None:
        """Successful batch embedding returns vectors."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.embeddings = [[0.1] * 1024, [0.2] * 1024]
        mock_client.embed.return_value = mock_response
        mock_client_class.return_value = mock_client

        provider = CohereEmbeddingProvider(api_key="test-key")
        vectors = provider.embed_batch(["Text 1", "Text 2"])

        assert len(vectors) == 2
        assert all(len(v) == 1024 for v in vectors)

    @patch("cohere.Client")
    def test_embed_batch_splits_large_batches(self, mock_client_class: MagicMock) -> None:
        """Large batches are split into chunks of 96."""
        mock_client = MagicMock()

        # Batch 1: 96 texts → 96 embeddings
        mock_response_1 = MagicMock()
        mock_response_1.embeddings = [[0.1] * 1024] * 96

        # Batch 2: 54 texts → 54 embeddings
        mock_response_2 = MagicMock()
        mock_response_2.embeddings = [[0.1] * 1024] * 54

        # Return different responses for each batch
        mock_client.embed.side_effect = [mock_response_1, mock_response_2]
        mock_client_class.return_value = mock_client

        provider = CohereEmbeddingProvider(api_key="test-key")
        texts = ["Text"] * 150
        vectors = provider.embed_batch(texts)

        assert len(vectors) == 150
        assert mock_client.embed.call_count == 2  # 96 + 54

    @patch("cohere.Client")
    def test_embed_batch_empty(self, mock_client_class: MagicMock) -> None:
        """Empty batch returns empty list."""
        provider = CohereEmbeddingProvider(api_key="test-key")
        vectors = provider.embed_batch([])

        assert vectors == []


class TestCohereMetadata:
    """Tests for metadata methods."""

    def test_get_dimensions(self, provider: CohereEmbeddingProvider) -> None:
        assert provider.get_dimensions() == 1024

    def test_get_model_name(self, provider: CohereEmbeddingProvider) -> None:
        assert provider.get_model_name() == "embed-multilingual-v3.0"
