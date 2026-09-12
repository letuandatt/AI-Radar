"""Embedding Provider Protocol.

Defines the interface for embedding providers (Ollama, Cohere, etc.).
All providers must implement this protocol to ensure swappable implementations.
"""

from typing import Protocol


class EmbeddingProvider(Protocol):
    """Protocol for embedding providers.

    Implementations must provide:
    - embed_text: Embed a single text string
    - embed_batch: Embed a list of text strings
    - get_dimensions: Return vector dimensions
    - get_model_name: Return model name
    """

    def embed_text(self, text: str) -> list[float]:
        """Embed a single text string.

        Args:
            text: Text to embed.

        Returns:
            List of floats representing the embedding vector.

        Raises:
            EmbeddingError: If embedding fails.
        """
        ...

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed a list of text strings.

        Args:
            texts: List of texts to embed.

        Returns:
            List of embedding vectors, one per input text.

        Raises:
            EmbeddingError: If embedding fails.
        """
        ...

    def get_dimensions(self) -> int:
        """Return the dimensionality of the embedding vectors.

        Returns:
            Integer representing vector dimensions.
        """
        ...

    def get_model_name(self) -> str:
        """Return the name of the embedding model.

        Returns:
            String representing the model name.
        """
        ...
