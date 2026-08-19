"""Storage abstraction layer and unified access path.

This module defines the application-level storage contract and provides
a centralized access path for the application to interact with the storage layer.
"""

from typing import Protocol, runtime_checkable

from app.config.settings import Settings
from app.core.logger import get_logger

logger = get_logger(__name__)


@runtime_checkable
class StorageProvider(Protocol):
    """The application-level storage contract.

    (Giữ nguyên docstring và interface từ T57)
    """

    def initialize(self) -> None: ...
    def is_ready(self) -> bool: ...
    def close(self) -> None: ...


# --- Unified Access Path (Singleton Management) ---

_storage_provider: StorageProvider | None = None


def initialize_storage(settings: Settings) -> None:
    """Initialize the storage layer and make it available application-wide.

    This function hides the underlying implementation (e.g., QdrantConnection)
    from the application core.
    """
    global _storage_provider

    if _storage_provider is not None:
        logger.warning("Storage is already initialized. Skipping.")
        return

    # Lazy import to keep the module import lightweight and avoid circular dependencies
    from app.storage.qdrant_client import QdrantConnection

    logger.info("Initializing storage abstraction")
    provider = QdrantConnection(settings)
    provider.initialize()

    _storage_provider = provider
    logger.info("Storage abstraction initialized successfully")


def get_storage() -> StorageProvider:
    """Return the unified storage access path.

    Raises:
        RuntimeError: If storage has not been initialized yet.
    """
    if _storage_provider is None:
        raise RuntimeError(
            "Storage is not initialized. "
            "Ensure initialize_storage() is called during application startup."
        )
    return _storage_provider


def shutdown_storage() -> None:
    """Shutdown the storage layer and release resources."""
    global _storage_provider

    if _storage_provider is not None:
        logger.info("Shutting down storage abstraction")
        _storage_provider.close()
        _storage_provider = None
        logger.info("Storage abstraction shut down successfully")
