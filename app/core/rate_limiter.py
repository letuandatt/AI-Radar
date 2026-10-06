"""Token Bucket rate limiter for API calls."""

import threading
import time


class TokenBucket:
    """
    Thread-safe Token Bucket rate limiter.

    ``wait_and_acquire`` polls with blocking ``time.sleep`` — safe for sync
    callers and for async callers that run through ``asyncio.to_thread`` (as
    ContentAnalyzer does). Calling it directly inside an event loop would
    block the loop; if that becomes a need, add an async variant first.

    Args:
        rate: Tokens added per second.
        capacity: Maximum tokens that can accumulate.
    """

    def __init__(self, rate: float, capacity: float) -> None:
        self.rate = rate
        self.capacity = capacity
        self.tokens = capacity
        self.last_update = time.time()
        self.lock = threading.Lock()

    def acquire(self, tokens: float = 1.0) -> bool:
        """
        Try to acquire tokens. Returns True if successful, False otherwise.

        Args:
            tokens: Number of tokens to acquire.

        Returns:
            True if tokens were acquired, False if rate limit exceeded.
        """
        with self.lock:
            now = time.time()
            elapsed = now - self.last_update
            self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
            self.last_update = now

            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            return False

    def wait_and_acquire(self, tokens: float = 1.0, timeout: float = 30.0) -> bool:
        """
        Wait until tokens are available or timeout.

        Args:
            tokens: Number of tokens to acquire.
            timeout: Maximum seconds to wait.

        Returns:
            True if tokens were acquired, False if timeout.
        """
        start = time.time()
        while time.time() - start < timeout:
            if self.acquire(tokens):
                return True
            time.sleep(0.1)
        return False
