"""Application exception hierarchy."""

from app.core.logger import get_logger

logger = get_logger(__name__)


class ApplicationError(Exception):
    """Base exception for expected application failures."""


class ConfigurationError(ApplicationError):
    """Raised when application configuration is invalid."""


class StartupError(ApplicationError):
    """Raised when application startup fails."""


def handle_application_exception(error: Exception) -> None:
    """Log and propagate an unhandled application exception."""
    logger.exception("Unhandled application exception")

    raise error
