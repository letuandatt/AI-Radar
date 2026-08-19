from unittest.mock import MagicMock, patch

from app.core.application import shutdown_application, start_application
from app.core.lifecycle import ApplicationLifecycle, ApplicationState


@patch("app.core.application.QdrantConnection")
@patch("app.core.application.get_settings")
def test_application_initializes_storage_with_centralized_config(mock_get_settings, mock_db_class):
    """Verify that storage is initialized using the centralized settings."""
    mock_settings = MagicMock()
    mock_get_settings.return_value = mock_settings

    mock_db_instance = MagicMock()
    mock_db_class.return_value = mock_db_instance

    lifecycle = ApplicationLifecycle()

    # Act: Start application
    start_application(lifecycle)

    # Assert: QdrantConnection was created with centralized settings
    mock_db_class.assert_called_once_with(mock_settings)
    mock_db_instance.initialize.assert_called_once()
    assert lifecycle.state is ApplicationState.RUNNING


@patch("app.core.application.QdrantConnection")
@patch("app.core.application.get_settings")
def test_application_shuts_down_storage_gracefully(mock_get_settings, mock_db_class):
    """Verify that storage is closed during application shutdown."""
    mock_settings = MagicMock()
    mock_get_settings.return_value = mock_settings

    mock_db_instance = MagicMock()
    mock_db_class.return_value = mock_db_instance

    lifecycle = ApplicationLifecycle()

    # Setup: Start app first
    start_application(lifecycle)

    # Act: Shutdown application
    shutdown_application(lifecycle)

    # Assert: Database connection was closed
    mock_db_instance.close.assert_called_once()
    assert lifecycle.state is ApplicationState.STOPPED
