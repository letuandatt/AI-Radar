"""Filter models for Metadata Retrieval.

Typed Pydantic models for defining metadata filters
used in Qdrant pre-filtering and retrieval queries.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

# =============================================================================
# Validation Error
# =============================================================================


class FilterSeverity(str, Enum):
    """Severity level for filter validation errors."""

    ERROR = "error"
    WARNING = "warning"


@dataclass(frozen=True)
class FilterValidationError:
    """A validation error for a metadata filter.

    Attributes:
        field: The field that failed validation.
        message: Human-readable error description.
        severity: Error or warning.
    """

    field: str
    message: str
    severity: FilterSeverity = FilterSeverity.ERROR


# =============================================================================
# Filter Models
# =============================================================================


class MetadataFilter(BaseModel):
    """Metadata filter for Qdrant pre-filtering.

    All fields are optional. Only non-None fields are applied.
    Top-level fields are AND-ed together.
    Multi-value fields (source_names, topics, entities) use OR logic
    within the field.

    Attributes:
        source_type: Filter by source type (e.g., "rss", "github").
        source_name: Filter by single source name.
        source_names: Filter by multiple source names (OR logic).
        topics: Filter by topics (OR logic within topics).
        entities: Filter by entities (OR logic within entities).
        published_after: Inclusive lower bound for published_at.
        published_before: Inclusive upper bound for published_at.
        has_url: If True, only items with source_url. If False, only without.
    """

    source_type: str | None = None
    source_name: str | None = None
    source_names: list[str] | None = None
    topics: list[str] | None = None
    entities: list[str] | None = None
    published_after: datetime | None = None
    published_before: datetime | None = None
    has_url: bool | None = None

    def is_empty(self) -> bool:
        """Return True if no filter conditions are set."""
        return all(
            value is None
            for value in [
                self.source_type,
                self.source_name,
                self.source_names,
                self.topics,
                self.entities,
                self.published_after,
                self.published_before,
                self.has_url,
            ]
        )

    def active_field_count(self) -> int:
        """Return the number of active filter fields."""
        count = 0
        if self.source_type is not None:
            count += 1
        if self.source_name is not None:
            count += 1
        if self.source_names is not None:
            count += 1
        if self.topics is not None:
            count += 1
        if self.entities is not None:
            count += 1
        if self.published_after is not None or self.published_before is not None:
            count += 1
        if self.has_url is not None:
            count += 1
        return count


class FilterCombination(BaseModel):
    """Combination of multiple metadata filters with logic operator.

    Attributes:
        filters: List of MetadataFilter to combine.
        operator: "and" or "or" logic between filters.
    """

    filters: list[MetadataFilter] = Field(default_factory=list)
    operator: str = "and"  # "and" or "or"

    def validate_operator(self) -> list[FilterValidationError]:
        """Validate the combination operator."""
        errors = []
        if self.operator not in ("and", "or"):
            errors.append(
                FilterValidationError(
                    field="operator",
                    message=f"Invalid operator '{self.operator}'. Must be 'and' or 'or'.",
                    severity=FilterSeverity.ERROR,
                )
            )
        return errors
