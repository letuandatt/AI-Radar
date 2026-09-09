"""Bootstrap logic for the Knowledge Repository.

This module bridges the application settings and the RepositoryInitializer,
keeping database-specific configuration details out of the application core.
"""

from pathlib import Path

from app.config.settings import Settings
from app.core.logger import get_logger
from app.services.repository.config import RepositoryConfig
from app.services.repository.initializer import RepositoryInitializer

logger = get_logger(__name__)


def initialize_knowledge_repository(settings: Settings) -> RepositoryInitializer:
    """Build and initialize the Knowledge Repository from application settings.

    Args:
        settings: Application settings.

    Returns:
        Initialized RepositoryInitializer instance.
    """
    config = RepositoryConfig(
        sqlite_path=Path("app/storage/knowledge/knowledge.db"),
        qdrant_url=settings.qdrant_url,
        qdrant_collection="knowledge_objects",
        bm25_index_path=Path("app/storage/search/bm25_index.pkl"),
        embedding_provider_type="ollama",
        ollama_base_url="http://localhost:11434",
        cohere_api_key=settings.cohere_api_key or None,
    )

    initializer = RepositoryInitializer(config)

    # Fail fast if critical components are unavailable
    state = initializer.initialize()

    logger.info(
        "Knowledge Repository initialized: sqlite=%d, vector=%d, bm25=%d, healthy=%s",
        state.sqlite_count,
        state.qdrant_count,
        state.bm25_count,
        state.is_healthy,
    )

    return initializer
