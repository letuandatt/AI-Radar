"""Application exception hierarchy."""

from app.core.logger import get_logger

logger = get_logger(__name__)


class ApplicationError(Exception):
    """Base exception for expected application failures."""


class ConfigurationError(ApplicationError):
    """Raised when application configuration is invalid."""


class StartupError(ApplicationError):
    """Raised when application startup fails."""


class DuplicateJobError(ApplicationError):
    """Raised when a job is registered more than once."""


def report_application_error(
    error: Exception,
    *,
    context: dict[str, object] | None = None,
) -> None:
    """Report an application error through the centralized logging path."""
    error_context = context or {}

    logger.error(
        "Application error | type=%s | message=%s | context=%s",
        type(error).__name__,
        str(error),
        error_context,
        exc_info=(type(error), error, error.__traceback__),
    )


def handle_application_exception(
    error: Exception,
    *,
    context: dict[str, object] | None = None,
) -> None:
    """Report and propagate an unhandled application exception."""
    report_application_error(error, context=context)

    raise error
