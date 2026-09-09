"""Repository configuration.

Centralizes all configuration for the Knowledge Repository stack.
"""

from dataclasses import dataclass
from pathlib import Path

from app.storage.vector.index_config import VectorIndexConfig


@dataclass(frozen=True)
class RepositoryConfig:
    """Configuration for the Knowledge Repository.

    Attributes:
        sqlite_path: Path to the SQLite database file.
        qdrant_url: Qdrant server URL.
        qdrant_collection: Qdrant collection name.
        qdrant_timeout: Qdrant request timeout in seconds.
        bm25_index_path: Path to the BM25 index pickle file.
        embedding_provider_type: Embedding provider type ("ollama" or "cohere").
        ollama_base_url: Ollama server URL.
        cohere_api_key: Cohere API key (required if provider is "cohere").
        auto_create_collections: Auto-create Qdrant collection if missing.
        backup_path: Directory for backup files.
        backup_retention_days: Number of days to retain backups.
        vector_index_config: HNSW and payload index configuration.
    """

    # SQLite
    sqlite_path: Path = Path("app/storage/knowledge/knowledge.db")

    # Qdrant
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "knowledge_objects"
    qdrant_timeout: int = 30

    # BM25
    bm25_index_path: Path = Path("app/storage/search/bm25_index.pkl")

    # Embedding
    embedding_provider_type: str = "ollama"
    ollama_base_url: str = "http://localhost:11434"
    cohere_api_key: str | None = None

    # Behavior
    auto_create_collections: bool = True

    # Backup
    backup_path: Path | None = None
    backup_retention_days: int = 7

    # Vector Index Config
    vector_index_config: VectorIndexConfig | None = None
