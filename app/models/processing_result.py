# app/models/processing_result.py
"""Data model for processing pipeline results.

Captures the metrics and outcomes of a single pipeline run,
including counts for each stage, failures, and timing information.
"""

from typing import Any

from pydantic import BaseModel, Field


class ProcessingResult(BaseModel):
    """Summary of a processing pipeline run.

    Attributes:
        total_input: Total number of input articles.
        cleaned: Number of articles successfully cleaned.
        normalized: Number of articles successfully normalized.
        extracted: Number of articles successfully extracted.
        objects_created: Number of new knowledge objects created.
        objects_updated: Number of existing knowledge objects updated.
        failed_objects: Number of articles that failed processing.
        skipped_objects: Number of articles skipped (already stored).
        processing_duration: Total processing time in seconds.
        errors: List of error details for failed articles.
    """

    total_input: int = Field(..., description="Total number of input articles")
    cleaned: int = Field(default=0, description="Articles successfully cleaned")
    normalized: int = Field(default=0, description="Articles successfully normalized")
    extracted: int = Field(default=0, description="Articles successfully extracted")
    objects_created: int = Field(default=0, description="New knowledge objects created")
    objects_updated: int = Field(default=0, description="Existing knowledge objects updated")
    failed_objects: int = Field(default=0, description="Articles that failed processing")
    skipped_objects: int = Field(default=0, description="Articles skipped (already stored)")
    processing_duration: float = Field(..., description="Total processing time in seconds")
    errors: list[dict[str, Any]] = Field(default_factory=list, description="List of error details")
