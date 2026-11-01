"""Tests for the LLM error taxonomy (Wiring & Fix Plan B3)."""

from app.core.exceptions import PermanentLLMError, TransientLLMError
from app.integrations.llm.error_taxonomy import classify_llm_error


class _FakeAPIStatusError(Exception):
    """Mimics groq.APIStatusError (has status_code + response)."""

    def __init__(self, status_code: int, headers: dict | None = None) -> None:
        super().__init__(f"status {status_code}")
        self.status_code = status_code
        self.response = type("R", (), {"headers": headers or {}})()


class _FakeHTTPStatusError(Exception):
    """Mimics httpx.HTTPStatusError (status on .response)."""

    def __init__(self, status_code: int, headers: dict | None = None) -> None:
        super().__init__(f"status {status_code}")
        self.response = type("R", (), {"status_code": status_code, "headers": headers or {}})()


class TestClassifyLLMError:
    def test_429_is_transient_with_retry_after(self):
        exc = _FakeAPIStatusError(429, headers={"retry-after": "5"})

        mapped = classify_llm_error(exc)

        assert isinstance(mapped, TransientLLMError)
        assert mapped.retry_after == 5.0

    def test_408_is_transient(self):
        assert isinstance(classify_llm_error(_FakeAPIStatusError(408)), TransientLLMError)

    def test_500_is_transient(self):
        assert isinstance(classify_llm_error(_FakeAPIStatusError(500)), TransientLLMError)

    def test_401_is_permanent(self):
        assert isinstance(classify_llm_error(_FakeAPIStatusError(401)), PermanentLLMError)

    def test_400_is_permanent(self):
        assert isinstance(classify_llm_error(_FakeAPIStatusError(400)), PermanentLLMError)

    def test_httpx_style_503_is_transient(self):
        assert isinstance(classify_llm_error(_FakeHTTPStatusError(503)), TransientLLMError)

    def test_timeout_error_is_transient(self):
        assert isinstance(classify_llm_error(TimeoutError("timed out")), TransientLLMError)

    def test_connection_error_is_transient(self):
        assert isinstance(classify_llm_error(ConnectionError("refused")), TransientLLMError)

    def test_unknown_error_is_permanent(self):
        assert isinstance(classify_llm_error(ValueError("bad")), PermanentLLMError)

    def test_taxonomy_errors_pass_through_unchanged(self):
        transient = TransientLLMError("already classified", retry_after=2.0)
        permanent = PermanentLLMError("already classified")

        assert classify_llm_error(transient) is transient
        assert classify_llm_error(permanent) is permanent
