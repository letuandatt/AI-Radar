"""Data models for source operational status."""

from datetime import datetime

from pydantic import BaseModel, Field


class SourceStatus(BaseModel):
    """Represents the operational status of a data source.

    Attributes:
        source_name: Unique name of the source.
        source_type: Type of source (rss, github, huggingface).
        is_active: Whether the source is currently active.
        last_checked: Timestamp of the last status check.
        error_message: Error message if the source is inactive.
    """

    source_name: str = Field(..., description="Unique name of the source")
    source_type: str = Field(..., description="Type of source (rss, github, huggingface)")
    is_active: bool = Field(default=True, description="Whether the source is currently active")
    last_checked: datetime | None = Field(
        default=None, description="Timestamp of the last status check"
    )
    error_message: str | None = Field(
        default=None, description="Error message if the source is inactive"
    )
