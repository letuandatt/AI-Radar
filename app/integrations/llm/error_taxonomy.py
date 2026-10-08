"""LLM error taxonomy: classify failures as transient (retryable) or permanent.

One classification, three consumers (Wiring & Fix Plan B3/B5):
retry decorator (only transient retries), provider chain (only transient/CB-open
falls back), and the future LLM Gateway.
"""

from app.core.exceptions import PermanentLLMError, TransientLLMError

_TRANSIENT_STATUS_CODES = {408, 409, 429}
_TIMEOUT_HINTS = ("timeout", "timed out")
_CONNECTION_HINTS = ("connect", "connection")


def classify_llm_error(exc: BaseException) -> BaseException:
    """Map a raw LLM call failure onto the error taxonomy.

    Unknown failures map to PermanentLLMError — safer to fail fast than to
    retry a bug. CircuitBreakerOpenError must be re-raised untouched by the
    caller so the provider chain can fall back instead of the retry loop
    spinning on an open circuit.
    """
    if isinstance(exc, (TransientLLMError, PermanentLLMError)):
        return exc

    status_code = _extract_status_code(exc)
    if status_code is not None:
        if status_code in _TRANSIENT_STATUS_CODES or status_code >= 500:
            return TransientLLMError(str(exc), retry_after=_extract_retry_after(exc))
        return PermanentLLMError(str(exc))

    name = type(exc).__name__.lower()
    message = str(exc).lower()
    if any(h in name or h in message for h in _TIMEOUT_HINTS) or any(
        h in name or h in message for h in _CONNECTION_HINTS
    ):
        return TransientLLMError(str(exc))

    return PermanentLLMError(str(exc))


def _extract_status_code(exc: BaseException) -> int | None:
    """Read an HTTP status code from groq/httpx-style exceptions, if any."""
    status_code = getattr(exc, "status_code", None)
    if isinstance(status_code, int):
        return status_code
    status_code = getattr(getattr(exc, "response", None), "status_code", None)
    if isinstance(status_code, int):
        return status_code
    return None


def _extract_retry_after(exc: BaseException) -> float | None:
    """Read a Retry-After header (seconds) from the exception response, if any."""
    headers = getattr(getattr(exc, "response", None), "headers", None)
    if headers is None:
        return None
    try:
        value = headers.get("retry-after")
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
