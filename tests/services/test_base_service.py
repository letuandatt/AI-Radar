"""Validation tests for Base Service implementation (T65)."""

import logging
from unittest.mock import MagicMock

import pytest

from app.services.base import BaseService, ServiceState, ServiceStateError


class ConcreteService(BaseService):
    """A concrete implementation of BaseService for testing."""

    def __init__(self, settings):
        super().__init__(settings)
        self.init_called = False
        self.start_called = False
        self.stop_called = False
        self.shutdown_called = False

    def _on_initialize(self):
        self.init_called = True

    def _on_start(self):
        self.start_called = True

    def _on_stop(self):
        self.stop_called = True

    def _on_shutdown(self):
        self.shutdown_called = True


def test_base_service_cannot_be_instantiated_directly():
    mock_settings = MagicMock()
    with pytest.raises(TypeError):
        BaseService(mock_settings)


def test_subclass_must_implement_on_start_method():
    class IncompleteService(BaseService):
        pass

    mock_settings = MagicMock()
    with pytest.raises(TypeError):
        IncompleteService(mock_settings)


def test_service_receives_settings_and_logger():
    mock_settings = MagicMock()
    service = ConcreteService(mock_settings)

    assert service._settings is mock_settings
    assert service._logger.name == "ConcreteService"
    assert service.state is ServiceState.CREATED


def test_service_lifecycle_transitions():
    mock_settings = MagicMock()
    service = ConcreteService(mock_settings)

    # Initialize
    service.initialize()
    assert service.state is ServiceState.INITIALIZED
    assert service.init_called is True

    # Start
    service.start()
    assert service.state is ServiceState.RUNNING
    assert service.start_called is True
    assert service.is_running is True

    # Stop
    service.stop()
    assert service.state is ServiceState.STOPPED
    assert service.stop_called is True
    assert service.is_running is False

    # Shutdown
    service.shutdown()
    assert service.shutdown_called is True


def test_initialize_fails_if_not_created():
    mock_settings = MagicMock()
    service = ConcreteService(mock_settings)
    service.initialize()

    with pytest.raises(ServiceStateError, match="Cannot initialize service from 'initialized'"):
        service.initialize()


def test_start_fails_if_not_initialized():
    mock_settings = MagicMock()
    service = ConcreteService(mock_settings)

    with pytest.raises(ServiceStateError, match="Cannot start service from 'created'"):
        service.start()


def test_stop_fails_if_created():
    mock_settings = MagicMock()
    service = ConcreteService(mock_settings)

    with pytest.raises(ServiceStateError, match="Cannot stop service from 'created'"):
        service.stop()


def test_shutdown_is_idempotent():
    mock_settings = MagicMock()
    service = ConcreteService(mock_settings)

    service.initialize()
    service.shutdown()  # Should call stop() then _on_shutdown()
    assert service.state is ServiceState.SHUTDOWN

    # Calling shutdown again should not raise
    service.shutdown()
    assert service.state is ServiceState.SHUTDOWN


def test_start_reports_error_and_propagates(caplog):
    """Verify that errors in _on_start() are reported centrally and propagated."""

    class FailingService(BaseService):
        def _on_start(self):
            raise ValueError("Business logic failed")

    mock_settings = MagicMock()
    service = FailingService(mock_settings)
    service.initialize()

    with caplog.at_level(logging.ERROR):
        with pytest.raises(ValueError, match="Business logic failed"):
            service.start()

    # Verify centralized error reporting was triggered
    assert any(
        record.levelno == logging.ERROR and "Business logic failed" in record.message
        for record in caplog.records
    )
    assert any("service_execution" in record.message for record in caplog.records)


def test_service_can_accept_additional_dependencies():
    """Validate that subclasses can inject dependencies beyond Settings.

    This ensures BaseService doesn't enforce a rigid constructor signature
    that prevents Dependency Injection of other components (e.g., Repositories).
    """

    class ServiceWithRepository(BaseService):
        def __init__(self, settings, repository):
            super().__init__(settings)
            self._repo = repository

        def _on_start(self):
            self._repo.fetch_data()

    mock_settings = MagicMock()
    mock_repo = MagicMock()

    service = ServiceWithRepository(mock_settings, mock_repo)
    service.initialize()
    service.start()

    mock_repo.fetch_data.assert_called_once()


def test_service_can_extend_with_custom_behavior():
    """Validate that subclasses can add new methods/properties.

    This ensures BaseService is not a 'sealed' class and allows
    business-specific logic to be exposed to callers (e.g., Pipelines).
    """

    class ExtendedDigestService(BaseService):
        def _on_start(self):
            pass

        def get_last_digest_date(self) -> str:
            return "2023-10-27"

    mock_settings = MagicMock()
    service = ExtendedDigestService(mock_settings)

    # Verify custom method is accessible and works
    assert service.get_last_digest_date() == "2023-10-27"


def test_error_context_reports_concrete_class_name(caplog):
    """Validate that error reporting uses the dynamic subclass name.

    This ensures that when an error occurs, the log clearly identifies
    WHICH service failed (e.g., 'DigestService'), not just 'BaseService'.
    """

    class SpecificBusinessService(BaseService):
        def _on_start(self):
            raise RuntimeError("Logic error in specific service")

    mock_settings = MagicMock()
    service = SpecificBusinessService(mock_settings)
    service.initialize()

    with caplog.at_level(logging.ERROR):
        with pytest.raises(RuntimeError):
            service.start()

    # Verify the log contains the specific class name
    assert "SpecificBusinessService" in caplog.text
    # Verify it does NOT just say "BaseService" in the context
    assert "service_name=BaseService" not in caplog.text
