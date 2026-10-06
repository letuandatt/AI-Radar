"""Shared FakeLLMProvider for tests (single place, scriptable behavior).

Implements the LLMProvider protocol so tests can inject a deterministic
provider instead of mocking raw LangChain models (Wiring & Fix Plan test
strategy 10.3).

Usage:
    provider = FakeLLMProvider(
        script=[ExtractionResult(...), TimeoutError("boom")],
        default_response=ExtractionResult(...),
    )
"""

from collections.abc import Callable
from typing import Any


class FakeLLMProvider:
    """Scriptable LLMProvider fake.

    Args:
        script: Per-call outcomes in order — a value is returned, a
            BaseException is raised. When exhausted, ``default_response``
            is used (or AssertionError if none).
        default_response: Response used once the script runs dry.
        call_hook: Invoked after every call (for measuring concurrency,
            latency, etc.).
        provider_name / model_name: Identity reported to callers.
    """

    def __init__(
        self,
        script: list[Any] | None = None,
        default_response: Any = None,
        call_hook: Callable[[], None] | None = None,
        provider_name: str = "fake",
        model_name: str = "fake-model",
    ) -> None:
        self._script = list(script or [])
        self._default_response = default_response
        self._call_hook = call_hook
        self._provider_name = provider_name
        self._model_name = model_name
        self.calls: list[tuple[str, str]] = []  # (method, prompt)
        self.schemas: list[type] = []

    def chat(self, prompt: str, **kwargs: object) -> str:
        self.calls.append(("chat", prompt))
        response = self._next_response()
        self._run_hook()
        if isinstance(response, BaseException):
            raise response
        return str(response)

    def structured_chat(self, prompt: str, schema: type) -> Any:
        self.calls.append(("structured_chat", prompt))
        self.schemas.append(schema)
        response = self._next_response()
        self._run_hook()
        if isinstance(response, BaseException):
            raise response
        return response

    def get_model_name(self) -> str:
        return self._model_name

    def get_provider_name(self) -> str:
        return self._provider_name

    def _next_response(self) -> Any:
        if self._script:
            return self._script.pop(0)
        if self._default_response is not None:
            return self._default_response
        raise AssertionError("FakeLLMProvider script exhausted and no default_response")

    def _run_hook(self) -> None:
        if self._call_hook is not None:
            self._call_hook()
