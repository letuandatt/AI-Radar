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


class BudgetExceededError(ApplicationError):
    """Raised when daily LLM budget is exceeded."""


class RateLimitWaitTimeoutError(ApplicationError):
    """Raised when waiting for a rate limiter token exceeds the configured timeout."""


class TransientLLMError(ApplicationError):
    """Retryable LLM failure: 408/429/5xx, timeout, connection errors.

    Carries ``retry_after`` (seconds) when the provider supplies a
    Retry-After hint, which the retry decorator honors over backoff.
    """

    def __init__(self, message: str, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class PermanentLLMError(ApplicationError):
    """Non-retryable LLM failure: 401/403/400, invalid model, schema errors.

    Unknown failures also map here — retrying a bug is worse than failing fast.
    """


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
