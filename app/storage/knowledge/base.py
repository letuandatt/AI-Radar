"""SQLite base utilities: connection management, retry, circuit breaker.

Provides the foundational reliability patterns used by SQLiteKnowledgeStore.
"""

import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from app.core.logger import get_logger

logger = get_logger(__name__)


# =============================================================================
# Circuit Breaker
# =============================================================================


class CircuitBreaker:
    """Simple circuit breaker for SQLite operations.

    States:
        CLOSED   — normal operation
        OPEN     — all calls fail immediately
        HALF_OPEN — allow one test call through

    Args:
        failure_threshold: Consecutive failures before opening circuit.
        recovery_timeout: Seconds to wait before trying half-open.
    """

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
    ) -> None:
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._state = self.CLOSED
        self._failure_count = 0
        self._last_failure_time: float = 0.0
        self._lock = threading.Lock()

    @property
    def state(self) -> str:
        with self._lock:
            if self._state == self.OPEN:
                # Check if recovery timeout has elapsed
                if time.monotonic() - self._last_failure_time >= self._recovery_timeout:
                    self._state = self.HALF_OPEN
            return self._state

    def record_success(self) -> None:
        """Record a successful call. Resets failure count."""
        with self._lock:
            self._failure_count = 0
            self._state = self.CLOSED

    def record_failure(self) -> None:
        """Record a failed call. May open the circuit."""
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.monotonic()
            if self._failure_count >= self._failure_threshold:
                self._state = self.OPEN
                logger.warning(
                    "CircuitBreaker OPEN after %d consecutive failures",
                    self._failure_count,
                )

    def allow_request(self) -> bool:
        """Check if a request is allowed through the circuit."""
        current_state = self.state
        if current_state == self.CLOSED:
            return True
        if current_state == self.HALF_OPEN:
            return True  # Allow one test request
        return False  # OPEN

    def reset(self) -> None:
        """Manually reset the circuit breaker."""
        with self._lock:
            self._state = self.CLOSED
            self._failure_count = 0


class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is open and request is rejected."""

    def __init__(self, message: str = "Circuit breaker is open") -> None:
        super().__init__(message)


# =============================================================================
# Retry Logic (GAP-001)
# =============================================================================


def retry_on_transient_error(
    max_retries: int = 3,
    base_delay: float = 0.5,
    max_delay: float = 10.0,
    retryable_exceptions: tuple[type[Exception], ...] = (sqlite3.OperationalError,),
) -> Any:
    """Decorator factory for retry with exponential backoff.

    Args:
        max_retries: Maximum number of retry attempts.
        base_delay: Initial delay in seconds.
        max_delay: Maximum delay cap in seconds.
        retryable_exceptions: Tuple of exception types to retry on.

    Returns:
        Decorator function.
    """

    def decorator(func: Any) -> Any:
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exception: Exception | None = None
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except retryable_exceptions as e:
                    last_exception = e
                    if attempt < max_retries:
                        delay = min(base_delay * (2**attempt), max_delay)
                        logger.warning(
                            "Transient error on attempt %d/%d: %s. Retrying in %.1fs...",
                            attempt + 1,
                            max_retries + 1,
                            str(e),
                            delay,
                        )
                        time.sleep(delay)
                    else:
                        logger.error(
                            "All %d attempts failed for %s: %s",
                            max_retries + 1,
                            func.__name__,
                            str(e),
                        )
            raise last_exception  # type: ignore[misc]

        wrapper.__name__ = func.__name__
        wrapper.__doc__ = func.__doc__
        return wrapper

    return decorator


# =============================================================================
# SQLite Connection Manager
# =============================================================================


class SQLiteConnectionManager:
    """Manages SQLite connections with timeout and thread safety.

    Args:
        db_path: Path to the SQLite database file.
        timeout: Transaction timeout in seconds.
    """

    def __init__(self, db_path: str | Path, timeout: float = 30.0) -> None:
        self._db_path = Path(db_path)
        self._timeout = timeout
        self._connection: sqlite3.Connection | None = None
        self._lock = threading.Lock()

    @property
    def db_path(self) -> Path:
        return self._db_path

    def get_connection(self) -> sqlite3.Connection:
        """Get or create a SQLite connection.

        Returns:
            Active sqlite3.Connection.

        Raises:
            sqlite3.Error: If connection cannot be established.
        """
        with self._lock:
            if self._connection is None:
                # Ensure parent directory exists
                self._db_path.parent.mkdir(parents=True, exist_ok=True)
                self._connection = sqlite3.connect(
                    str(self._db_path),
                    timeout=self._timeout,
                    check_same_thread=False,
                )
                # Enable WAL mode for better concurrent read performance
                self._connection.execute("PRAGMA journal_mode=WAL")
                # Enable foreign keys
                self._connection.execute("PRAGMA foreign_keys=ON")
                logger.debug(
                    "SQLite connection established: %s (timeout=%.1fs)",
                    self._db_path,
                    self._timeout,
                )
            return self._connection

    def close(self) -> None:
        """Close the SQLite connection."""
        with self._lock:
            if self._connection is not None:
                self._connection.close()
                self._connection = None
                logger.debug("SQLite connection closed: %s", self._db_path)
