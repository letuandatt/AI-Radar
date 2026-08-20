import logging

from app.core.lifecycle import ApplicationLifecycle
from app.core.logger import get_logger, initialize_logging


def test_logging_initialization_configures_root_logger():
    initialize_logging()

    root_logger = logging.getLogger()

    assert root_logger.level == logging.INFO
    assert root_logger.handlers


def test_logging_initialization_does_not_duplicate_handlers():
    initialize_logging()

    root_logger = logging.getLogger()
    handler_count = len(root_logger.handlers)

    initialize_logging()

    assert len(root_logger.handlers) == handler_count


def test_shared_logger_access_returns_named_logger():
    logger = get_logger("app.test")

    assert isinstance(logger, logging.Logger)
    assert logger.name == "app.test"


def test_different_components_can_access_shared_logging():
    first_logger = get_logger("app.core")
    second_logger = get_logger("app.services")

    assert first_logger.name == "app.core"
    assert second_logger.name == "app.services"


def test_application_lifecycle_transition_is_logged(caplog):
    lifecycle = ApplicationLifecycle()

    with caplog.at_level(logging.INFO):
        lifecycle.begin_initialization()

    assert "Application lifecycle transition" in caplog.text
    assert "created -> initializing" in caplog.text
