import pytest

from app.core.retry import retry_on_transient_error


def test_retries_on_exception():
    call_count = 0

    @retry_on_transient_error(max_retries=3, base_delay=0.01, exceptions=(ValueError,))
    def flaky_func():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ValueError("transient")
        return "success"

    assert flaky_func() == "success"
    assert call_count == 3


def test_raises_after_max_retries():
    @retry_on_transient_error(max_retries=2, base_delay=0.01, exceptions=(ValueError,))
    def always_fails():
        raise ValueError("permanent")

    with pytest.raises(ValueError):
        always_fails()
