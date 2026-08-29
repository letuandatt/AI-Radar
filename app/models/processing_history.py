"""Data model for processing history entries.

Each entry represents a single pipeline run result,
wrapped with metadata for tracking and retrieval.
"""

import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, Field

from .processing_result import ProcessingResult


class ProcessingHistoryEntry(BaseModel):
    """A single entry in the processing history log.

    Wraps a ProcessingResult with run-level metadata
    to enable historical tracking and retrieval.

    Attributes:
        run_id: Unique identifier for this pipeline run.
        completed_at: Timestamp when the pipeline run completed.
        result: The processing result containing all metrics.
    """

    run_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique identifier for this pipeline run",
    )
    completed_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp when the pipeline run completed",
    )
    result: ProcessingResult = Field(
        ..., description="The processing result containing all metrics"
    )
