# tests/test_application_integration.py
from unittest.mock import MagicMock, patch

from app.core.application import shutdown_application, start_application
from app.core.lifecycle import ApplicationLifecycle, ApplicationState


@patch("app.core.application.shutdown_storage")
@patch("app.core.application.initialize_storage")
@patch("app.core.application.get_settings")
def test_application_initializes_storage_via_abstraction(
    mock_get_settings, mock_init_storage, mock_shutdown_storage
):
    """Verify that application uses the storage abstraction layer."""
    mock_settings = MagicMock()
    mock_get_settings.return_value = mock_settings

    lifecycle = ApplicationLifecycle()

    # Act
    start_application(lifecycle)

    # Assert: initialize_storage was called with centralized settings
    mock_init_storage.assert_called_once_with(mock_settings)
    assert lifecycle.state is ApplicationState.RUNNING


@patch("app.core.application.shutdown_storage")
@patch("app.core.application.initialize_storage")
@patch("app.core.application.get_settings")
def test_application_shuts_down_storage_via_abstraction(
    mock_get_settings, mock_init_storage, mock_shutdown_storage
):
    """Verify that application shuts down storage via abstraction layer."""
    mock_get_settings.return_value = MagicMock()

    lifecycle = ApplicationLifecycle()

    # Setup
    start_application(lifecycle)

    # Act
    shutdown_application(lifecycle)

    # Assert: shutdown_storage was called
    mock_shutdown_storage.assert_called_once()
    assert lifecycle.state is ApplicationState.STOPPED
