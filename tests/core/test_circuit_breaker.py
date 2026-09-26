import time

from app.core.circuit_breaker import CircuitBreaker, CircuitState


def test_initial_state_is_closed():
    cb = CircuitBreaker(failure_threshold=3)
    assert cb.state == CircuitState.CLOSED
    assert cb.allow_request() is True


def test_opens_after_threshold_failures():
    cb = CircuitBreaker(failure_threshold=2, recovery_timeout=1.0)
    cb.record_failure()
    assert cb.state == CircuitState.CLOSED
    cb.record_failure()
    assert cb.state == CircuitState.OPEN
    assert cb.allow_request() is False


def test_transitions_to_half_open_after_timeout():
    cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.1)
    cb.record_failure()
    assert cb.state == CircuitState.OPEN
    time.sleep(0.15)
    assert cb.state == CircuitState.HALF_OPEN
    assert cb.allow_request() is True


def test_closes_on_success_from_half_open():
    cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.1)
    cb.record_failure()
    time.sleep(0.15)
    assert cb.state == CircuitState.HALF_OPEN
    cb.record_success()
    assert cb.state == CircuitState.CLOSED
