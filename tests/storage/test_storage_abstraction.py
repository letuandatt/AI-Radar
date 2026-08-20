"""Validation tests for Storage Abstraction (T59).

This module ensures that the storage abstraction boundaries are strictly enforced
and that the application core remains completely unaware of the underlying
database implementation (e.g., Qdrant).
"""

import inspect
from unittest.mock import MagicMock

from app.storage.base import StorageProvider
from app.storage.qdrant_client import QdrantConnection


def test_storage_implementation_satisfies_protocol():
    """Validate that QdrantConnection structurally satisfies StorageProvider at runtime."""
    mock_settings = MagicMock()
    connection = QdrantConnection(mock_settings)

    # Because StorageProvider is @runtime_checkable, we can use isinstance
    assert isinstance(connection, StorageProvider), (
        "QdrantConnection must satisfy the StorageProvider protocol"
    )


def test_database_specific_details_not_exposed_to_core():
    """Validate that app/core/application.py has no knowledge of Qdrant.

    This enforces the architectural rule: Core must not depend on
    database-specific implementation details.
    """
    import app.core.application as app_core

    # Read the actual source code of the application core module
    source_code = inspect.getsource(app_core)

    # Ensure no database-specific keywords exist in the core orchestration layer
    assert "qdrant" not in source_code.lower(), (
        "Application core must not contain database-specific details (e.g., Qdrant)"
    )

    # Ensure no direct import of the specific client module
    assert "qdrant_client" not in dir(app_core), (
        "Application core must not import qdrant_client directly"
    )


def test_application_uses_storage_via_abstraction():
    """Validate that application core interacts with storage only via the abstraction path."""
    import app.core.application as app_core

    # Verify that the core imports and uses the abstraction functions
    assert hasattr(app_core, "initialize_storage"), (
        "Application core must use initialize_storage from the abstraction layer"
    )
    assert hasattr(app_core, "shutdown_storage"), (
        "Application core must use shutdown_storage from the abstraction layer"
    )

    # Verify it does NOT hold a direct reference to the concrete implementation
    assert not hasattr(app_core, "_database"), (
        "Application core should not hold a direct reference to a concrete database instance"
    )
