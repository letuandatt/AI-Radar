"""Unit tests for EmbeddingProviderFactory."""

import pytest

from app.services.embedding.cohere_provider import CohereEmbeddingProvider
from app.services.embedding.factory import EmbeddingProviderFactory
from app.services.embedding.ollama_provider import OllamaEmbeddingProvider


class TestFactoryCreate:
    """Tests for create method."""

    def test_create_ollama(self) -> None:
        """Factory creates OllamaEmbeddingProvider."""
        provider = EmbeddingProviderFactory.create("ollama")

        assert isinstance(provider, OllamaEmbeddingProvider)
        assert provider.get_model_name() == "nomic-embed-text"

    def test_create_cohere(self) -> None:
        """Factory creates CohereEmbeddingProvider with API key."""
        provider = EmbeddingProviderFactory.create("cohere", cohere_api_key="test-key")

        assert isinstance(provider, CohereEmbeddingProvider)
        assert provider.get_model_name() == "embed-multilingual-v3.0"

    def test_create_cohere_without_api_key(self) -> None:
        """Factory raises ValueError if Cohere API key missing."""
        with pytest.raises(ValueError, match="cohere_api_key is required"):
            EmbeddingProviderFactory.create("cohere")

    def test_create_invalid_provider(self) -> None:
        """Factory raises ValueError for unknown provider."""
        with pytest.raises(ValueError, match="Unknown provider"):
            EmbeddingProviderFactory.create("invalid")

    def test_create_case_insensitive(self) -> None:
        """Factory accepts provider names case-insensitively."""
        provider1 = EmbeddingProviderFactory.create("OLLAMA")
        provider2 = EmbeddingProviderFactory.create("Ollama")

        assert isinstance(provider1, OllamaEmbeddingProvider)
        assert isinstance(provider2, OllamaEmbeddingProvider)
