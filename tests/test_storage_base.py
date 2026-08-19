import inspect
from unittest.mock import MagicMock, patch

import pytest

import app.storage.base as storage_base
from app.storage.base import (
    StorageProvider,
    get_storage,
    initialize_storage,
    shutdown_storage,
)


def test_storage_provider_protocol_exists():
    assert StorageProvider is not None


def test_storage_provider_defines_required_lifecycle_methods():
    required_methods = {"initialize", "is_ready", "close"}
    protocol_members = {
        name for name, _ in inspect.getmembers(StorageProvider) if not name.startswith("_")
    }
    assert required_methods.issubset(protocol_members)


# --- Tests for Unified Access Path ---


@pytest.fixture(autouse=True)
def reset_storage_state():
    """Reset the global storage state before and after each test."""
    storage_base._storage_provider = None
    yield
    storage_base._storage_provider = None


@patch("app.storage.qdrant_client.QdrantConnection")
def test_initialize_storage_creates_and_initializes_provider(mock_qdrant_class):
    mock_settings = MagicMock()
    mock_provider_instance = MagicMock()
    mock_qdrant_class.return_value = mock_provider_instance

    initialize_storage(mock_settings)

    mock_qdrant_class.assert_called_once_with(mock_settings)
    mock_provider_instance.initialize.assert_called_once()
    assert storage_base._storage_provider is not None


def test_get_storage_returns_initialized_provider():
    mock_provider = MagicMock()
    storage_base._storage_provider = mock_provider

    result = get_storage()

    assert result is mock_provider


def test_get_storage_raises_error_if_not_initialized():
    with pytest.raises(RuntimeError, match="Storage is not initialized"):
        get_storage()


def test_shutdown_storage_closes_and_clears_provider():
    mock_provider = MagicMock()
    storage_base._storage_provider = mock_provider

    shutdown_storage()

    mock_provider.close.assert_called_once()
    assert storage_base._storage_provider is None


def test_shutdown_storage_is_safe_if_not_initialized():
    # Should not raise any error
    shutdown_storage()
