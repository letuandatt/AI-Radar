"""Public contracts for adding one URL to the knowledge collection."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.services.knowledge.url_fetcher import canonical_url


class ManualAddRequest(BaseModel):
    """A public article URL and an optional reader-supplied title."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    url: str = Field(min_length=1, max_length=2048)
    title: str | None = Field(default=None, min_length=1, max_length=300)

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        """Validate syntax before any network or provider operation."""
        return canonical_url(value)


class ManualAddResult(BaseModel):
    """SQLite persistence and optional downstream outcomes are reported separately."""

    knowledge_id: str
    status: Literal["created", "existing"]
    indexing: Literal["ready", "partial", "unchanged"]
    analysis: Literal["ready", "failed", "unchanged"]
    importance: Literal["ready", "failed", "skipped", "unchanged"]
    content_truncated: bool = False


class ManualAddError(Exception):
    """A safe, fixed public error; never include upstream payloads or credentials."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
