import logging
from unittest.mock import MagicMock, patch

import pytest

from app.core.exceptions import StartupError
from app.storage.qdrant_client import (
    DatabaseState,
    DatabaseStateError,
    QdrantConnection,
)


@pytest.fixture
def mock_settings():
    """Provide a mock Settings object for testing."""
    settings = MagicMock()
    settings.qdrant_url = "http://localhost:6333"
    settings.qdrant_api_key = "test-api-key"
    return settings


def test_connection_starts_in_created_state(mock_settings):
    conn = QdrantConnection(mock_settings)
    assert conn.state is DatabaseState.CREATED


@patch("qdrant_client.QdrantClient")
def test_initialize_transitions_to_initialized(mock_client_class, mock_settings):
    mock_client_instance = MagicMock()
    mock_client_class.return_value = mock_client_instance

    conn = QdrantConnection(mock_settings)
    conn.initialize()

    assert conn.state is DatabaseState.INITIALIZED
    mock_client_class.assert_called_once_with(
        url="http://localhost:6333",
        api_key="test-api-key",
    )
    mock_client_instance.get_collections.assert_called_once()


def test_initialize_fails_if_not_created(mock_settings):
    conn = QdrantConnection(mock_settings)
    conn._state = DatabaseState.INITIALIZED  # Force invalid state

    with pytest.raises(DatabaseStateError):
        conn.initialize()


@patch("qdrant_client.QdrantClient")
def test_initialize_raises_startup_error_on_connection_failure(
    mock_client_class, mock_settings, caplog
):
    mock_client_instance = MagicMock()
    mock_client_instance.get_collections.side_effect = Exception("Connection refused")
    mock_client_class.return_value = mock_client_instance

    conn = QdrantConnection(mock_settings)

    with caplog.at_level(logging.INFO):
        with pytest.raises(StartupError, match="Failed to initialize Qdrant database"):
            conn.initialize()

    assert conn.state is DatabaseState.CREATED  # State must not change on failure


@patch("qdrant_client.QdrantClient")
def test_close_transitions_to_closed(mock_client_class, mock_settings):
    mock_client_instance = MagicMock()
    mock_client_class.return_value = mock_client_instance

    conn = QdrantConnection(mock_settings)
    conn.initialize()
    conn.close()

    assert conn.state is DatabaseState.CLOSED
    mock_client_instance.close.assert_called_once()


@patch("qdrant_client.QdrantClient")
def test_close_is_safe_to_call_twice(mock_client_class, mock_settings):
    mock_client_instance = MagicMock()
    mock_client_class.return_value = mock_client_instance

    conn = QdrantConnection(mock_settings)
    conn.initialize()
    conn.close()
    conn.close()  # Second call should not raise

    assert conn.state is DatabaseState.CLOSED


def test_close_fails_if_not_initialized(mock_settings):
    conn = QdrantConnection(mock_settings)

    with pytest.raises(DatabaseStateError):
        conn.close()


@patch("qdrant_client.QdrantClient")
def test_get_client_returns_client_when_initialized(mock_client_class, mock_settings):
    """Verify that get_client returns the singleton instance when ready."""
    mock_client_instance = MagicMock()
    mock_client_class.return_value = mock_client_instance

    conn = QdrantConnection(mock_settings)
    conn.initialize()

    # Act
    client = conn.get_client()

    # Assert: Returns the exact same instance (Connection Reuse)
    assert client is mock_client_instance


def test_get_client_raises_error_when_created(mock_settings):
    """Verify that get_client fails if connection is not initialized."""
    conn = QdrantConnection(mock_settings)

    with pytest.raises(DatabaseStateError, match="Cannot get client from 'created' state"):
        conn.get_client()


@patch("qdrant_client.QdrantClient")
def test_get_client_raises_error_when_closed(mock_client_class, mock_settings):
    """Verify that get_client fails if connection has been closed."""
    mock_client_instance = MagicMock()
    mock_client_class.return_value = mock_client_instance

    conn = QdrantConnection(mock_settings)
    conn.initialize()
    conn.close()

    with pytest.raises(DatabaseStateError, match="Cannot get client from 'closed' state"):
        conn.get_client()


@patch("qdrant_client.QdrantClient")
def test_close_handles_network_error_gracefully(mock_client_class, mock_settings, caplog):
    """Verify that close() transitions to CLOSED even if client.close() fails."""
    mock_client_instance = MagicMock()
    mock_client_instance.close.side_effect = Exception("Network error during close")
    mock_client_class.return_value = mock_client_instance

    conn = QdrantConnection(mock_settings)
    conn.initialize()

    with caplog.at_level(logging.ERROR):
        conn.close()  # Should not raise

    assert conn.state is DatabaseState.CLOSED
    assert "Failed to close Qdrant client gracefully" in caplog.text
