"""Circuit Breaker pattern for transient error protection."""

import threading
import time
from enum import Enum

from app.core.logger import get_logger

logger = get_logger(__name__)


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is open and requests are rejected."""

    pass


class CircuitBreaker:
    """
    Thread-safe Circuit Breaker.

    States:
    - CLOSED: Normal operation, requests pass through.
    - OPEN: Failures exceeded threshold, requests are rejected immediately.
    - HALF_OPEN: Testing if service recovered, allows one request through.
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        name: str = "default",
    ) -> None:
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._name = name

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time = 0.0
        self._lock = threading.RLock()

    @property
    def state(self) -> CircuitState:
        with self._lock:
            if self._state == CircuitState.OPEN:
                if time.time() - self._last_failure_time >= self._recovery_timeout:
                    self._state = CircuitState.HALF_OPEN
            return self._state

    def record_success(self) -> None:
        with self._lock:
            self._failure_count = 0
            if self._state == CircuitState.HALF_OPEN:
                logger.info("CircuitBreaker [%s]: HALF_OPEN -> CLOSED", self._name)
            self._state = CircuitState.CLOSED

    def record_failure(self) -> None:
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()

            if self._failure_count >= self._failure_threshold:
                if self._state != CircuitState.OPEN:
                    logger.warning(
                        "CircuitBreaker [%s]: OPEN (failures=%d)", self._name, self._failure_count
                    )
                self._state = CircuitState.OPEN

    def allow_request(self) -> bool:
        state = self.state
        if state == CircuitState.CLOSED:
            return True
        if state == CircuitState.HALF_OPEN:
            return True
        return False

    def reset(self) -> None:
        with self._lock:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._last_failure_time = 0.0

    def ensure_closed(self) -> None:
        if self.state == CircuitState.OPEN:
            raise CircuitBreakerOpenError("CircuitBreaker is open! Cannot proceed. Need to reset.")
        return
