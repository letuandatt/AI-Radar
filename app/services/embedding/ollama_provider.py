"""Ollama Embedding Provider.

Primary embedding provider using local Ollama server.
Model: nomic-embed-text (768 dimensions).
"""

import ollama

from app.core.logger import get_logger
from app.storage.knowledge.base import CircuitBreaker, retry_on_transient_error

logger = get_logger(__name__)


class EmbeddingError(Exception):
    """Raised when embedding operation fails."""

    pass


class OllamaEmbeddingProvider:
    """Ollama-based embedding provider.

    Uses local Ollama server for embedding generation.
    Default model: nomic-embed-text (768 dimensions).

    Args:
        model: Ollama model name (default: nomic-embed-text).
        base_url: Ollama server URL (default: http://localhost:11434).
        timeout: Request timeout in seconds (default: 30).
        max_retries: Max retries for transient errors (default: 3).
        circuit_breaker: Optional CircuitBreaker instance.
    """

    def __init__(
        self,
        model: str = "nomic-embed-text",
        base_url: str = "http://localhost:11434",
        timeout: float = 30.0,
        max_retries: int = 3,
        circuit_breaker: CircuitBreaker | None = None,
    ) -> None:
        self._model = model
        self._base_url = base_url
        self._timeout = timeout
        self._max_retries = max_retries
        self._circuit_breaker = circuit_breaker or CircuitBreaker()
        self._client = ollama.Client(host=base_url)

    @retry_on_transient_error(
        max_retries=3,
        base_delay=0.5,
        retryable_exceptions=(Exception,),
    )
    def embed_text(self, text: str) -> list[float]:
        """Embed a single text using Ollama.

        Args:
            text: Text to embed.

        Returns:
            Embedding vector (768 dimensions).

        Raises:
            EmbeddingError: If embedding fails.
        """
        if not self._circuit_breaker.allow_request():
            raise EmbeddingError("Circuit breaker is open")

        try:
            response = self._client.embed(
                model=self._model,
                input=text,
            )
            self._circuit_breaker.record_success()
            return response["embeddings"][0]  # type: ignore[no-any-return]
        except Exception as e:
            self._circuit_breaker.record_failure()
            logger.error("Ollama embedding failed: %s", e)
            raise EmbeddingError(f"Ollama embedding failed: {e}") from e

    @retry_on_transient_error(
        max_retries=3,
        base_delay=0.5,
        retryable_exceptions=(Exception,),
    )
    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts using Ollama.

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

        try:
            response = self._client.embed(
                model=self._model,
                input=texts,
            )
            self._circuit_breaker.record_success()
            return response["embeddings"]  # type: ignore[no-any-return]
        except Exception as e:
            self._circuit_breaker.record_failure()
            logger.error("Ollama batch embedding failed: %s", e)
            raise EmbeddingError(f"Ollama batch embedding failed: {e}") from e

    def get_dimensions(self) -> int:
        """Return embedding dimensions for nomic-embed-text."""
        return 768

    def get_model_name(self) -> str:
        """Return the Ollama model name."""
        return self._model
