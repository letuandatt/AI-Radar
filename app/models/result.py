"""Data models for pipeline execution results.

This module defines the canonical structures representing the outcome
of an acquisition or processing pipeline run.
"""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class SourceError:
    """Represents an error that occurred while processing a specific source.

    Attributes:
        source_name: The unique name of the source that failed.
        source_type: The type of the source (e.g., 'rss', 'github', 'huggingface').
        error_type: The category of the error (e.g., 'NetworkError', 'ParsingError').
        error_message: A human-readable description of the error.
    """

    source_name: str
    source_type: str
    error_type: str
    error_message: str


@dataclass
class AcquisitionResult:
    """Represents the aggregated result of a single acquisition pipeline run.

    Attributes:
        timestamp: The exact time the pipeline execution started.
        total_sources: Total number of sources attempted.
        successful_sources: Number of sources that completed successfully.
        failed_sources: Number of sources that failed (after retries).
        total_articles: Total number of RawArticles successfully parsed and stored.
        execution_time: Total duration of the pipeline run in seconds.
        errors: A list of detailed errors for each failed source.
    """

    timestamp: datetime
    total_sources: int
    successful_sources: int
    failed_sources: int
    total_articles: int
    execution_time: float
    errors: list[SourceError] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert the result to a dictionary for JSON serialization."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "total_sources": self.total_sources,
            "successful_sources": self.successful_sources,
            "failed_sources": self.failed_sources,
            "total_articles": self.total_articles,
            "execution_time": self.execution_time,
            "errors": [
                {
                    "source_name": err.source_name,
                    "source_type": err.source_type,
                    "error_type": err.error_type,
                    "error_message": err.error_message,
                }
                for err in self.errors
            ],
        }
