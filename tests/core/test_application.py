"""Integration tests for Application Lifecycle with ComponentRegistry."""

from unittest.mock import MagicMock, patch

import pytest

from app.core.application import (
    get_component,
    shutdown_application,
    start_application,
)
from app.core.lifecycle import ApplicationLifecycle, ApplicationState


@patch("app.core.application._shutdown_storage")
@patch("app.core.application._init_storage")
@patch("app.core.application._shutdown_scheduler")
@patch("app.core.application._init_scheduler")
@patch("app.core.application._shutdown_logging")
@patch("app.core.application._init_logging")
def test_application_initializes_components_via_registry(
    mock_init_logging,
    mock_shutdown_logging,
    mock_init_scheduler,
    mock_shutdown_scheduler,
    mock_init_storage,
    mock_shutdown_storage,
):
    """Verify that application uses ComponentRegistry to initialize components."""
    mock_init_logging.return_value = "logging"
    mock_init_scheduler.return_value = MagicMock()
    mock_init_storage.return_value = MagicMock()

    lifecycle = ApplicationLifecycle()

    # Act
    start_application(lifecycle)

    # Assert: All init functions were called by the registry
    mock_init_logging.assert_called_once()
    mock_init_scheduler.assert_called_once()
    mock_init_storage.assert_called_once()

    assert lifecycle.state is ApplicationState.RUNNING


@patch("app.core.application._shutdown_storage")
@patch("app.core.application._init_storage")
@patch("app.core.application._shutdown_scheduler")
@patch("app.core.application._init_scheduler")
@patch("app.core.application._shutdown_logging")
@patch("app.core.application._init_logging")
def test_application_shuts_down_components_via_registry(
    mock_init_logging,
    mock_shutdown_logging,
    mock_init_scheduler,
    mock_shutdown_scheduler,
    mock_init_storage,
    mock_shutdown_storage,
):
    """Verify that application shuts down components via registry."""
    mock_init_logging.return_value = "logging"
    mock_init_scheduler.return_value = MagicMock()
    mock_init_storage.return_value = MagicMock()

    lifecycle = ApplicationLifecycle()

    # Setup
    start_application(lifecycle)

    # Act
    shutdown_application(lifecycle)

    # Assert: All shutdown functions were called by the registry
    mock_shutdown_logging.assert_called_once()
    mock_shutdown_scheduler.assert_called_once()
    mock_shutdown_storage.assert_called_once()

    assert lifecycle.state is ApplicationState.STOPPED


@patch("app.core.application._shutdown_storage")
@patch("app.core.application._init_storage")
@patch("app.core.application._shutdown_scheduler")
@patch("app.core.application._init_scheduler")
@patch("app.core.application._shutdown_logging")
@patch("app.core.application._init_logging")
def test_get_component_retrieves_initialized_component(
    mock_init_logging,
    mock_shutdown_logging,
    mock_init_scheduler,
    mock_shutdown_scheduler,
    mock_init_storage,
    mock_shutdown_storage,
):
    """Verify that get_component returns the correct instance."""
    mock_scheduler = MagicMock()
    mock_init_scheduler.return_value = mock_scheduler
    mock_init_logging.return_value = "logging"
    mock_init_storage.return_value = MagicMock()

    lifecycle = ApplicationLifecycle()
    start_application(lifecycle)

    # Assert: Components can be retrieved by name
    assert get_component("scheduler") is mock_scheduler
    assert get_component("logging") == "logging"


@patch("app.core.application._shutdown_storage")
@patch("app.core.application._init_storage")
@patch("app.core.application._shutdown_scheduler")
@patch("app.core.application._init_scheduler")
@patch("app.core.application._shutdown_logging")
@patch("app.core.application._init_logging")
def test_application_components_initialized_in_priority_order(
    mock_init_logging,
    mock_shutdown_logging,
    mock_init_scheduler,
    mock_shutdown_scheduler,
    mock_init_storage,
    mock_shutdown_storage,
):
    """Verify that components are initialized in ascending priority order."""
    call_order = []
    mock_init_logging.side_effect = lambda: call_order.append("logging") or "logging"
    mock_init_scheduler.side_effect = lambda: call_order.append("scheduler") or MagicMock()
    mock_init_storage.side_effect = lambda: call_order.append("storage") or MagicMock()

    lifecycle = ApplicationLifecycle()
    start_application(lifecycle)

    assert call_order == ["logging", "scheduler", "storage"]


@patch("app.core.application._shutdown_storage")
@patch("app.core.application._init_storage")
@patch("app.core.application._shutdown_scheduler")
@patch("app.core.application._init_scheduler")
@patch("app.core.application._shutdown_logging")
@patch("app.core.application._init_logging")
def test_application_components_shutdown_in_reverse_priority_order(
    mock_init_logging,
    mock_shutdown_logging,
    mock_init_scheduler,
    mock_shutdown_scheduler,
    mock_init_storage,
    mock_shutdown_storage,
):
    """Verify that components are shut down in descending priority order."""
    mock_init_logging.return_value = "logging"
    mock_init_scheduler.return_value = MagicMock()
    mock_init_storage.return_value = MagicMock()

    shutdown_order = []
    mock_shutdown_logging.side_effect = lambda x: shutdown_order.append("logging")
    mock_shutdown_scheduler.side_effect = lambda x: shutdown_order.append("scheduler")
    mock_shutdown_storage.side_effect = lambda x: shutdown_order.append("storage")

    lifecycle = ApplicationLifecycle()
    start_application(lifecycle)
    shutdown_application(lifecycle)

    assert shutdown_order == ["storage", "scheduler", "logging"]


@patch("app.core.application._shutdown_storage")
@patch("app.core.application._init_storage")
@patch("app.core.application._shutdown_scheduler")
@patch("app.core.application._init_scheduler")
@patch("app.core.application._shutdown_logging")
@patch("app.core.application._init_logging")
def test_application_rollback_when_storage_fails(
    mock_init_logging,
    mock_shutdown_logging,
    mock_init_scheduler,
    mock_shutdown_scheduler,
    mock_init_storage,
    mock_shutdown_storage,
):
    """Verify that initialized components are rolled back if a later component fails."""
    mock_init_logging.return_value = "logging"
    mock_init_scheduler.return_value = MagicMock()
    mock_init_storage.side_effect = RuntimeError("Storage connection failed")

    lifecycle = ApplicationLifecycle()

    with pytest.raises(RuntimeError, match="Storage connection failed"):
        start_application(lifecycle)

    # Logging and Scheduler were initialized, so they must be shut down (rolled back)
    mock_shutdown_logging.assert_called_once()
    mock_shutdown_scheduler.assert_called_once()
    # Storage failed to init, so its shutdown should NOT be called by the registry rollback
    mock_shutdown_storage.assert_not_called()

    assert lifecycle.state is ApplicationState.STOPPED


@patch("app.core.application._shutdown_storage")
@patch("app.core.application._init_storage")
@patch("app.core.application._shutdown_scheduler")
@patch("app.core.application._init_scheduler")
@patch("app.core.application._shutdown_logging")
@patch("app.core.application._init_logging")
def test_get_component_returns_real_instances(
    mock_init_logging,
    mock_shutdown_logging,
    mock_init_scheduler,
    mock_shutdown_scheduler,
    mock_init_storage,
    mock_shutdown_storage,
):
    """Verify that get_component returns the actual instances created during startup."""
    mock_scheduler = MagicMock()
    mock_init_logging.return_value = "logging"
    mock_init_scheduler.return_value = mock_scheduler
    mock_init_storage.return_value = MagicMock()

    lifecycle = ApplicationLifecycle()
    start_application(lifecycle)

    # Assert: Components can be retrieved and are the exact instances created
    assert get_component("scheduler") is mock_scheduler
    assert get_component("logging") == "logging"

    # Cleanup
    shutdown_application(lifecycle)
