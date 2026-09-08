"""Embedding Provider Factory.

Factory for creating embedding providers by name.
"""

from app.core.logger import get_logger
from app.services.embedding.cohere_provider import CohereEmbeddingProvider
from app.services.embedding.ollama_provider import OllamaEmbeddingProvider
from app.services.embedding.provider import EmbeddingProvider
from app.storage.knowledge.base import CircuitBreaker

logger = get_logger(__name__)


class EmbeddingProviderFactory:
    """Factory for creating embedding providers.

    Supported providers:
    - "ollama": Ollama local server (nomic-embed-text, 768 dims)
    - "cohere": Cohere API (embed-multilingual-v3.0, 1024 dims)
    """

    @staticmethod
    def create(
        provider_name: str,
        cohere_api_key: str | None = None,
        ollama_base_url: str = "http://localhost:11434",
        circuit_breaker: CircuitBreaker | None = None,
    ) -> EmbeddingProvider:
        """Create an embedding provider by name.

        Args:
            provider_name: Provider name ("ollama" or "cohere").
            cohere_api_key: Cohere API key (required for "cohere").
            ollama_base_url: Ollama server URL (for "ollama").
            circuit_breaker: Optional CircuitBreaker instance.

        Returns:
            EmbeddingProvider instance.

        Raises:
            ValueError: If provider_name is invalid.
            ValueError: If cohere_api_key is missing for "cohere".
        """
        provider_name = provider_name.lower()

        if provider_name == "ollama":
            logger.info("Creating Ollama embedding provider")
            return OllamaEmbeddingProvider(
                base_url=ollama_base_url,
                circuit_breaker=circuit_breaker,
            )

        if provider_name == "cohere":
            if not cohere_api_key:
                raise ValueError(
                    "cohere_api_key is required for Cohere provider. "
                    "Set COHERE_API_KEY environment variable."
                )
            logger.info("Creating Cohere embedding provider")
            return CohereEmbeddingProvider(
                api_key=cohere_api_key,
                circuit_breaker=circuit_breaker,
            )

        raise ValueError(f"Unknown provider: {provider_name}. Supported providers: ollama, cohere")
