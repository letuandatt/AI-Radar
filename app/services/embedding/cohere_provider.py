"""Cohere Embedding Provider.

Fallback embedding provider using Cohere API.
Model: embed-multilingual-v3.0 (1024 dimensions).
"""

import cohere

from app.core.logger import get_logger
from app.storage.knowledge.base import CircuitBreaker, retry_on_transient_error

logger = get_logger(__name__)


class EmbeddingError(Exception):
    """Raised when embedding operation fails."""

    pass


class CohereEmbeddingProvider:
    """Cohere-based embedding provider.

    Uses Cohere API for embedding generation.
    Default model: embed-multilingual-v3.0 (1024 dimensions).

    Args:
        api_key: Cohere API key.
        model: Cohere model name (default: embed-multilingual-v3.0).
        max_retries: Max retries for transient errors (default: 3).
        circuit_breaker: Optional CircuitBreaker instance.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "embed-multilingual-v3.0",
        max_retries: int = 3,
        circuit_breaker: CircuitBreaker | None = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._max_retries = max_retries
        self._circuit_breaker = circuit_breaker or CircuitBreaker()
        self._client = cohere.Client(api_key=api_key)

    @retry_on_transient_error(
        max_retries=3,
        base_delay=0.5,
        retryable_exceptions=(Exception,),
    )
    def embed_text(self, text: str) -> list[float]:
        """Embed a single text using Cohere.

        Args:
            text: Text to embed.

        Returns:
            Embedding vector (1024 dimensions).

        Raises:
            EmbeddingError: If embedding fails.
        """
        if not self._circuit_breaker.allow_request():
            raise EmbeddingError("Circuit breaker is open")

        try:
            response = self._client.embed(
                texts=[text],
                model=self._model,
                input_type="search_document",
            )
            self._circuit_breaker.record_success()
            return response.embeddings[0]  # type: ignore[index]
        except Exception as e:
            self._circuit_breaker.record_failure()
            logger.error("Cohere embedding failed: %s", e)
            raise EmbeddingError(f"Cohere embedding failed: {e}") from e

    @retry_on_transient_error(
        max_retries=3,
        base_delay=0.5,
        retryable_exceptions=(Exception,),
    )
    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts using Cohere.

        Args:
            texts: List of texts to embed.

        Returns:
            List of embedding vectors.

        Raises:
            EmbeddingError: If embedding fails.
        """
        if not self._circuit_breaker.allow_request():
            raise EmbeddingError("Circuit breaker is open")

        if not texts:
            return []

        # Cohere has batch size limit of 96
        all_embeddings = []  # type: ignore[var-annotated]
        batch_size = 96

        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            try:
                response = self._client.embed(
                    texts=batch,
                    model=self._model,
                    input_type="search_document",
                )
                all_embeddings.extend(response.embeddings)
            except Exception as e:
                self._circuit_breaker.record_failure()
                logger.error("Cohere batch embedding failed: %s", e)
                raise EmbeddingError(f"Cohere batch embedding failed: {e}") from e

        self._circuit_breaker.record_success()
        return all_embeddings

    def get_dimensions(self) -> int:
        """Return embedding dimensions for embed-multilingual-v3.0."""
        return 1024

    def get_model_name(self) -> str:
        """Return the Cohere model name."""
        return self._model
