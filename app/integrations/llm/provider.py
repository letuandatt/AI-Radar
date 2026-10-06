"""LLM Provider Protocol."""

from typing import Protocol, TypeVar, runtime_checkable

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


@runtime_checkable
class LLMProvider(Protocol):
    """Protocol for LLM providers."""

    def chat(self, prompt: str, **kwargs: object) -> str:
        """
        Send a chat completion request.

        Args:
            prompt: The prompt string.
            **kwargs: Additional provider-specific arguments.

        Returns:
            The response text.
        """
        ...

    def structured_chat(self, prompt: str, schema: type[T]) -> T:
        """
        Send a chat completion request with structured output.

        Args:
            prompt: The prompt string.
            schema: Pydantic model class for structured output.

        Returns:
            Instance of the schema populated with LLM response.
        """
        ...

    def estimate_cost(self, prompt: str) -> float:
        """
        Estimate the USD cost of a request BEFORE running it (B6).

        Free/local providers return 0.0. Estimates are always upper-bound
        inputs to CostTracker.check_budget — never billing data.

        Args:
            prompt: The prompt string.

        Returns:
            Estimated cost in USD.
        """
        ...

    def get_model_name(self) -> str:
        """Get the model name."""
        ...

    def get_provider_name(self) -> str:
        """Get the provider name (e.g., 'ollama', 'groq')."""
        ...
