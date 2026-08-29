"""Data models for processing state tracking.

Defines the item-level state structure used to track the processing
progress of each article through the pipeline stages, enabling
checkpoint/resume and replay of failed items.
"""

from datetime import datetime, timezone

from pydantic import BaseModel, Field


class ItemState(BaseModel):
    """Processing state of a single item identified by content_hash.

    Attributes:
        content_hash: SHA-256 hash identifying the item.
        stage: Last completed stage ("cleaned", "normalized", "extracted", "stored").
        status: Processing status ("success", "failed").
        error_type: Type of error if failed (e.g., "normalization_error").
        error_message: Human-readable error message if failed.
        attempt_count: Number of processing attempts for this item.
        processor_version: Version of the processor that last handled this item.
        updated_at: Timestamp of the last state update.
    """

    content_hash: str = Field(..., description="SHA-256 hash identifying the item")

    stage: str = Field(
        ..., description="Last completed stage: cleaned, normalized, extracted, stored"
    )

    status: str = Field(..., description="Processing status: success, failed")

    error_type: str | None = Field(default=None, description="Type of error if processing failed")

    error_message: str | None = Field(
        default=None, description="Human-readable error message if failed"
    )

    attempt_count: int = Field(default=1, description="Number of processing attempts")

    processor_version: str = Field(
        default="1.0.0", description="Version of the processing pipeline"
    )

    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Last state update timestamp",
    )


class ProcessingState(BaseModel):
    """Aggregate processing state across all items.

    Attributes:
        items: Mapping from content_hash to item processing state.
        last_run: Timestamp of the last pipeline run.
    """

    items: dict[str, ItemState] = Field(
        default_factory=dict, description="Item states keyed by content_hash"
    )
    last_run: datetime | None = Field(
        default=None, description="Timestamp of the last pipeline run"
    )
