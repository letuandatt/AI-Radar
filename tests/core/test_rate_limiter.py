"""Tests for TokenBucket rate limiter."""

import threading
import time

from app.core.rate_limiter import TokenBucket


class TestTokenBucket:
    def test_initial_capacity(self):
        bucket = TokenBucket(rate=10.0, capacity=10.0)
        assert bucket.acquire(10.0) is True

    def test_acquire_exceeds_capacity(self):
        bucket = TokenBucket(rate=10.0, capacity=5.0)
        assert bucket.acquire(10.0) is False

    def test_refill_over_time(self):
        bucket = TokenBucket(rate=100.0, capacity=10.0)
        bucket.acquire(10.0)  # Empty the bucket
        time.sleep(0.1)  # Wait for refill (10 tokens)
        assert bucket.acquire(5.0) is True

    def test_thread_safety(self):
        bucket = TokenBucket(rate=1000.0, capacity=100.0)
        results = []

        def worker():
            for _ in range(10):
                results.append(bucket.acquire(1.0))

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All should succeed (100 capacity, 100 attempts)
        assert sum(results) == 100

    def test_wait_and_acquire_success(self):
        bucket = TokenBucket(rate=100.0, capacity=1.0)
        bucket.acquire(1.0)  # Empty
        assert bucket.wait_and_acquire(1.0, timeout=1.0) is True

    def test_wait_and_acquire_timeout(self):
        bucket = TokenBucket(rate=0.1, capacity=1.0)  # Very slow refill
        bucket.acquire(1.0)  # Empty
        assert bucket.wait_and_acquire(1.0, timeout=0.1) is False
