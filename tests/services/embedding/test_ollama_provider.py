"""Unit tests for OllamaEmbeddingProvider."""

from unittest.mock import MagicMock, patch

import pytest

from app.services.embedding.ollama_provider import (
    EmbeddingError,
    OllamaEmbeddingProvider,
)
from app.storage.knowledge.base import CircuitBreaker


@pytest.fixture
def provider() -> OllamaEmbeddingProvider:
    return OllamaEmbeddingProvider()


class TestOllamaEmbedText:
    """Tests for embed_text method."""

    @patch("ollama.Client")
    def test_embed_text_success(self, mock_client_class: MagicMock) -> None:
        """Successful embedding returns vector."""
        mock_client = MagicMock()
        mock_client.embed.return_value = {"embeddings": [[0.1] * 768]}
        mock_client_class.return_value = mock_client

        provider = OllamaEmbeddingProvider()
        vector = provider.embed_text("Test text")

        assert len(vector) == 768
        assert all(isinstance(x, float) for x in vector)

    @patch("ollama.Client")
    def test_embed_text_circuit_open(self, mock_client_class: MagicMock) -> None:
        """Circuit breaker open raises EmbeddingError."""
        cb = CircuitBreaker(failure_threshold=1)
        cb.record_failure()  # Open circuit

        provider = OllamaEmbeddingProvider(circuit_breaker=cb)

        with pytest.raises(EmbeddingError, match="Circuit breaker"):
            provider.embed_text("Test text")

    @patch("ollama.Client")
    def test_embed_text_retry_on_failure(self, mock_client_class: MagicMock) -> None:
        """Retries on transient failure."""
        mock_client = MagicMock()
        mock_client.embed.side_effect = [
            Exception("Connection refused"),
            Exception("Connection refused"),
            {"embeddings": [[0.1] * 768]},
        ]
        mock_client_class.return_value = mock_client

        provider = OllamaEmbeddingProvider(max_retries=3)
        vector = provider.embed_text("Test text")

        assert len(vector) == 768
        assert mock_client.embed.call_count == 3


class TestOllamaEmbedBatch:
    """Tests for embed_batch method."""

    @patch("ollama.Client")
    def test_embed_batch_success(self, mock_client_class: MagicMock) -> None:
        """Successful batch embedding returns vectors."""
        mock_client = MagicMock()
        mock_client.embed.return_value = {"embeddings": [[0.1] * 768, [0.2] * 768]}
        mock_client_class.return_value = mock_client

        provider = OllamaEmbeddingProvider()
        vectors = provider.embed_batch(["Text 1", "Text 2"])

        assert len(vectors) == 2
        assert all(len(v) == 768 for v in vectors)

    @patch("ollama.Client")
    def test_embed_batch_empty(self, mock_client_class: MagicMock) -> None:
        """Empty batch returns empty list."""
        provider = OllamaEmbeddingProvider()
        vectors = provider.embed_batch([])

        assert vectors == []


class TestOllamaMetadata:
    """Tests for metadata methods."""

    def test_get_dimensions(self, provider: OllamaEmbeddingProvider) -> None:
        assert provider.get_dimensions() == 768

    def test_get_model_name(self, provider: OllamaEmbeddingProvider) -> None:
        assert provider.get_model_name() == "nomic-embed-text"
