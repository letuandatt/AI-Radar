"""Retry decorator with exponential backoff and jitter."""

import functools
import random
import time
from collections.abc import Callable
from typing import Any, TypeVar

from app.core.logger import get_logger

logger = get_logger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


def retry_on_transient_error(
    max_retries: int = 3,
    base_delay: float = 0.5,
    max_delay: float = 30.0,
    backoff_factor: float = 2.0,
    jitter: float = 0.1,
    exceptions: tuple[type[BaseException], ...] = (Exception,),
) -> Callable[[F], F]:
    """
    Decorator that retries a function on transient errors with exponential backoff.
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exception = None
            for attempt in range(1, max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt == max_retries:
                        logger.error(
                            "Retry exhausted for %s after %d attempts: %s",
                            func.__name__,
                            max_retries,
                            str(e),
                        )
                        raise

                    delay = min(base_delay * (backoff_factor ** (attempt - 1)), max_delay)
                    delay += random.uniform(0, delay * jitter)

                    logger.warning(
                        "Transient error on attempt %d/%d for %s: %s. Retrying in %.2fs...",
                        attempt,
                        max_retries,
                        func.__name__,
                        str(e),
                        delay,
                    )
                    time.sleep(delay)
            raise last_exception  # type: ignore[misc]

        return wrapper  # type: ignore[return-value]

    return decorator
