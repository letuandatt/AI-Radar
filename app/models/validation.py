"""Data models for validation results.

This module defines the canonical structures representing validation outcomes,
used by validators across the system (Source Validation, LLM Output Validation, etc.).
"""

from typing import Any

from pydantic import BaseModel, Field


class ValidationResult(BaseModel):
    """Represents the outcome of a validation operation.

    This model is used consistently across all validators in the system,
    providing a unified interface for validation results.

    Attributes:
        is_valid: Whether the validation passed successfully.
        error_message: Human-readable error message if validation failed.
        details: Additional structured details about the validation (optional).
    """

    is_valid: bool = Field(..., description="Whether the validation passed successfully.")
    error_message: str | None = Field(
        default=None, description="Error message if validation failed."
    )
    details: dict[str, Any] = Field(
        default_factory=dict, description="Additional validation details."
    )

    @classmethod
    def success(cls, details: dict[str, Any] | None = None) -> "ValidationResult":
        """Create a successful validation result."""
        return cls(is_valid=True, error_message=None, details=details or {})

    @classmethod
    def failure(
        cls, error_message: str, details: dict[str, Any] | None = None
    ) -> "ValidationResult":
        """Create a failed validation result."""
        return cls(is_valid=False, error_message=error_message, details=details or {})
