"""Retrieval response models.

Typed Pydantic models for the Unified Retrieval Interface.
These models are MCP-001 ready and can be serialized to JSON
for OpenAPI spec generation.
"""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

# =============================================================================
# Enums
# =============================================================================


class RetrievalMethod(str, Enum):
    """Retrieval strategy method."""

    VECTOR = "vector"
    KEYWORD = "keyword"
    HYBRID = "hybrid"


# =============================================================================
# Error Contract (Typed Exceptions)
# =============================================================================


class RetrievalError(Exception):
    """Base exception for retrieval errors."""

    pass


class RetrievalQueryTooLongError(RetrievalError):
    """Raised when query exceeds maximum length."""

    def __init__(self, query_length: int, max_length: int = 1000) -> None:
        self.query_length = query_length
        self.max_length = max_length
        super().__init__(f"Query length {query_length} exceeds maximum of {max_length} characters")


class RetrievalServiceUnavailableError(RetrievalError):
    """Raised when the retrieval service is temporarily unavailable."""

    def __init__(self, message: str = "Retrieval service is temporarily unavailable") -> None:
        super().__init__(message)


class InvalidRetrievalMethodError(RetrievalError):
    """Raised when an invalid retrieval method is specified."""

    def __init__(self, method: str) -> None:
        self.method = method
        valid_methods = [m.value for m in RetrievalMethod]
        super().__init__(f"Invalid retrieval method '{method}'. Valid methods: {valid_methods}")


# =============================================================================
# Response Models
# =============================================================================


class RetrievalResult(BaseModel):
    """A single retrieval result with full metadata and citations.

    Attributes:
        knowledge_id: Internal UUID of the knowledge object.
        title: Title of the knowledge item.
        source_url: Original source URL (citation).
        content_snippet: First 300 characters of content.
        source_type: Source type (rss, github, huggingface).
        source_name: Source name.
        published_at: Publication timestamp.
        topics: Extracted topics.
        entities: Extracted entities.
        relevance_score: Relevance score from search.
        retrieval_method: Method used to retrieve this result.
    """

    knowledge_id: str
    title: str
    source_url: str | None = None
    content_snippet: str = ""
    source_type: str = ""
    source_name: str = ""
    published_at: datetime | None = None
    topics: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    relevance_score: float = 0.0
    retrieval_method: str = RetrievalMethod.HYBRID.value


class RetrievalResponse(BaseModel):
    """Response from a retrieval search operation.

    Attributes:
        query: The original search query.
        results: List of retrieval results.
        total_matches: Total number of matches found.
        retrieval_time_ms: Time taken for retrieval in milliseconds.
        filters_applied: Description of filters applied (if any).
        method: Retrieval method used.
    """

    query: str
    results: list[RetrievalResult] = Field(default_factory=list)
    total_matches: int = 0
    retrieval_time_ms: float = 0.0
    filters_applied: dict[str, Any] | None = None
    method: str = RetrievalMethod.HYBRID.value
