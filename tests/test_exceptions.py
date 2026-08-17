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

    records = [
        record
        for record in caplog.records
        if record.name == "app.core.exceptions" and record.levelno == logging.ERROR
    ]

    assert len(records) == 1


def test_unexpected_exception_is_logged_and_propagated(caplog):
    error = RuntimeError("Unexpected failure")

    with caplog.at_level(logging.ERROR):
        with pytest.raises(RuntimeError):
            handle_application_exception(error)

    records = [
        record
        for record in caplog.records
        if record.name == "app.core.exceptions" and record.levelno == logging.ERROR
    ]

    assert len(records) == 1


def test_configuration_error_is_logged_and_propagated(caplog):
    error = ConfigurationError("Configuration is invalid")

    with caplog.at_level(logging.ERROR):
        with pytest.raises(ConfigurationError):
            handle_application_exception(error)

    records = [
        record
        for record in caplog.records
        if record.name == "app.core.exceptions" and record.levelno == logging.ERROR
    ]

    assert len(records) == 1


def test_exception_is_logged_once(caplog):
    error = ApplicationError("Failure")

    with caplog.at_level(logging.ERROR):
        with pytest.raises(ApplicationError):
            handle_application_exception(error)

    records = [
        record
        for record in caplog.records
        if record.name == "app.core.exceptions" and record.levelno == logging.ERROR
    ]

    assert len(records) == 1


def test_application_error_report_contains_error_information(caplog):
    error = ApplicationError("Known application failure")

    with caplog.at_level(logging.ERROR):
        with pytest.raises(ApplicationError):
            handle_application_exception(
                error,
                context={
                    "operation": "application_runtime",
                    "lifecycle_state": "running",
                },
            )

    assert len(caplog.records) == 1

    record = caplog.records[0]

    assert record.name == "app.core.exceptions"
    assert record.levelno == logging.ERROR
    assert "ApplicationError" in record.message
    assert "Known application failure" in record.message
    assert "application_runtime" in record.message
    assert "running" in record.message


def test_error_context_is_captured(caplog):
    error = RuntimeError("Runtime failure")

    context = {
        "operation": "application_runtime",
        "lifecycle_state": "initializing",
    }

    with caplog.at_level(logging.ERROR):
        with pytest.raises(RuntimeError):
            handle_application_exception(error, context=context)

    assert len(caplog.records) == 1

    record = caplog.records[0]

    assert "operation" in record.message
    assert "application_runtime" in record.message
    assert "lifecycle_state" in record.message
    assert "initializing" in record.message
