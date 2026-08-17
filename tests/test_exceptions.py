import logging

import pytest

from app.core.exceptions import (
    ApplicationError,
    ConfigurationError,
    StartupError,
    handle_application_exception,
)


def test_configuration_error_is_application_error():
    error = ConfigurationError("Invalid configuration")

    assert isinstance(error, ApplicationError)


def test_startup_error_is_application_error():
    error = StartupError("Startup failed")

    assert isinstance(error, ApplicationError)


def test_application_exception_is_propagated():
    error = ApplicationError("Application failure")

    with pytest.raises(ApplicationError, match="Application failure"):
        handle_application_exception(error)


def test_unexpected_exception_is_propagated():
    error = RuntimeError("Unexpected failure")

    with pytest.raises(RuntimeError, match="Unexpected failure"):
        handle_application_exception(error)


def test_known_application_exception_is_logged_and_propagated(caplog):
    error = ApplicationError("Known application failure")

    with caplog.at_level(logging.ERROR):
        with pytest.raises(ApplicationError):
            handle_application_exception(error)

    assert "Unhandled application exception" in caplog.text


def test_unexpected_exception_is_logged_and_propagated(caplog):
    error = RuntimeError("Unexpected failure")

    with caplog.at_level(logging.ERROR):
        with pytest.raises(RuntimeError):
            handle_application_exception(error)

    assert "Unhandled application exception" in caplog.text


def test_configuration_error_is_logged_and_propagated(caplog):
    error = ConfigurationError("Configuration is invalid")

    with caplog.at_level(logging.ERROR):
        with pytest.raises(ConfigurationError):
            handle_application_exception(error)

    assert "Unhandled application exception" in caplog.text


def test_exception_is_logged_once(caplog):
    error = ApplicationError("Failure")

    with caplog.at_level(logging.ERROR):
        with pytest.raises(ApplicationError):
            handle_application_exception(error)

    records = [
        record for record in caplog.records if record.message == "Unhandled application exception"
    ]

    assert len(records) == 1
