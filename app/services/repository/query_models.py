"""Query models for Repository Access Service.

Typed Pydantic models for INFRA-002 (Web Dashboard) and MCP-001 (Read-Only MCP).
These models define the API contract for knowledge repository access.
"""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

# =============================================================================
# Enums
# =============================================================================


class SortDirection(str, Enum):
    """Sort direction for query results."""

    ASC = "asc"
    DESC = "desc"


class SortField(str, Enum):
    """Sortable fields for knowledge queries."""

    CREATED_AT = "created_at"
    PUBLISHED_AT = "published_at"
    TITLE = "title"


class PaginationMode(str, Enum):
    """Pagination mode for list operations."""

    CURSOR = "cursor"
    PAGE = "page"


# =============================================================================
# Error Contract (Typed Exceptions)
# =============================================================================


class RepositoryError(Exception):
    """Base exception for repository errors."""

    pass


class RepositoryNotFoundError(RepositoryError):
    """Raised when a requested resource is not found."""

    def __init__(self, resource_type: str = "item", resource_id: str = "") -> None:
        self.resource_type = resource_type
        self.resource_id = resource_id
        super().__init__(
            f"{resource_type} not found: {resource_id}"
            if resource_id
            else f"{resource_type} not found"
        )


class RepositoryUnavailableError(RepositoryError):
    """Raised when the repository is temporarily unavailable."""

    def __init__(self, message: str = "Repository is temporarily unavailable") -> None:
        super().__init__(message)


class InvalidQueryError(RepositoryError):
    """Raised when a query is malformed or invalid."""

    def __init__(self, message: str = "Invalid query") -> None:
        super().__init__(message)


# =============================================================================
# Query Models
# =============================================================================


class KnowledgeQuery(BaseModel):
    """Query parameters for knowledge search and filtering.

    Attributes:
        source_type: Filter by source type.
        source_name: Filter by source name.
        published_after: Inclusive lower bound for published_at.
        published_before: Inclusive upper bound for published_at.
        search_text: Free-text search (reserved for Sprint 18 retrieval).
        sort_field: Field to sort by.
        sort_direction: Sort direction.
        pagination_mode: Cursor-based or page-based pagination.
        cursor: Cursor for cursor-based pagination (created_at ISO string).
        limit: Maximum number of items per page.
        offset: Offset for page-based pagination.
    """

    source_type: str | None = None
    source_name: str | None = None
    published_after: datetime | None = None
    published_before: datetime | None = None
    search_text: str | None = None

    sort_field: SortField = SortField.CREATED_AT
    sort_direction: SortDirection = SortDirection.DESC

    pagination_mode: PaginationMode = PaginationMode.CURSOR
    cursor: str | None = None
    limit: int = Field(default=50, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


# =============================================================================
# Response Models
# =============================================================================


class PageInfo(BaseModel):
    """Pagination metadata for list responses.

    Attributes:
        next_cursor: Cursor for the next page (cursor-based pagination).
        has_next: Whether there are more items after this page.
        has_prev: Whether there are items before this page.
        total: Total number of items (page-based pagination only).
    """

    next_cursor: str | None = None
    has_next: bool = False
    has_prev: bool = False
    total: int | None = None


class KnowledgeItemSummary(BaseModel):
    """Summary of a knowledge item for list responses.

    Attributes:
        id: Internal UUID.
        title: Item title.
        source_type: Source type (rss, github, huggingface).
        source_name: Source name.
        published_at: Publication timestamp.
        created_at: Creation timestamp.
        content_hash: SHA-256 hash of content.
        topics: Extracted topics.
    """

    id: str
    title: str
    source_type: str
    source_name: str
    published_at: datetime | None = None
    created_at: datetime | None = None
    content_hash: str
    topics: list[str] = Field(default_factory=list)


class KnowledgeListResponse(BaseModel):
    """Response for list operations.

    Attributes:
        items: List of knowledge item summaries.
        total: Total number of items (may be None for cursor pagination).
        page_info: Pagination metadata.
    """

    items: list[KnowledgeItemSummary] = Field(default_factory=list)
    total: int | None = None
    page_info: PageInfo = Field(default_factory=PageInfo)


class KnowledgeDetailResponse(BaseModel):
    """Full detail of a knowledge item.

    Attributes:
        id: Internal UUID.
        title: Item title.
        source_type: Source type.
        source_name: Source name.
        external_id: External identifier from source.
        source_url: Original source URL.
        content_text: Full content text.
        content_hash: SHA-256 hash of content.
        metadata: Extraction metadata (summary, topics, entities, relevance).
        published_at: Publication timestamp.
        created_at: Creation timestamp.
        updated_at: Last update timestamp.
        citations: Related source URLs.
    """

    id: str
    title: str
    source_type: str
    source_name: str
    external_id: str | None = None
    source_url: str | None = None
    content_text: str
    content_hash: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    published_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    citations: list[str] = Field(default_factory=list)


# =============================================================================
# Statistics Models
# =============================================================================


class SourceHealth(BaseModel):
    """Health status of a knowledge source.

    Attributes:
        source_type: Source type.
        source_name: Source name.
        total_items: Total items from this source.
        last_published_at: Timestamp of the most recent published item.
        last_created_at: Timestamp of the most recent created item.
    """

    source_type: str
    source_name: str
    total_items: int
    last_published_at: str | None = None
    last_created_at: str | None = None


class RepositoryStatistics(BaseModel):
    """Aggregate statistics for the knowledge repository.

    Attributes:
        total_items: Total number of knowledge items.
        by_source: Item counts grouped by source.
        by_date_range: Item counts grouped by date (last 30 days).
        last_updated: Timestamp of the most recent update.
    """

    total_items: int
    by_source: dict[str, int] = Field(default_factory=dict)
    by_date_range: dict[str, int] = Field(default_factory=dict)
    last_updated: str | None = None
