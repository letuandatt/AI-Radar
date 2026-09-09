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


def create_application_services(initializer: "RepositoryInitializer"):
    """Create ApplicationService and all its dependencies from an initializer.

    This factory function keeps database-specific property access
    (e.g., initializer.qdrant_store) out of the application core module.

    Args:
        initializer: Initialized RepositoryInitializer.

    Returns:
        Fully wired ApplicationService instance.
    """
    from app.services.app_service import ApplicationService
    from app.services.repository.access_service import RepositoryAccessService
    from app.services.repository.lifecycle_service import RepositoryLifecycleService

    access_service = RepositoryAccessService(
        sqlite_store=initializer.sqlite_store,
    )

    lifecycle_service = RepositoryLifecycleService(
        config=initializer.config,
        sqlite_store=initializer.sqlite_store,
        qdrant_store=initializer.qdrant_store,
        bm25_index=initializer.bm25_index,
    )
    lifecycle_service.start()

    return ApplicationService(
        initializer=initializer,
        access_service=access_service,
        lifecycle_service=lifecycle_service,
    )
