"""Unit tests for Repository query models."""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.services.repository.query_models import (
    InvalidQueryError,
    KnowledgeDetailResponse,
    KnowledgeItemSummary,
    KnowledgeListResponse,
    KnowledgeQuery,
    PageInfo,
    PaginationMode,
    RepositoryNotFoundError,
    RepositoryStatistics,
    RepositoryUnavailableError,
    SortDirection,
    SortField,
    SourceHealth,
)

# =============================================================================
# KnowledgeQuery Tests
# =============================================================================


class TestKnowledgeQuery:
    """Tests for KnowledgeQuery model."""

    def test_default_values(self) -> None:
        """Default query has sensible defaults."""
        query = KnowledgeQuery()

        assert query.source_type is None
        assert query.source_name is None
        assert query.published_after is None
        assert query.published_before is None
        assert query.search_text is None
        assert query.sort_field == SortField.CREATED_AT
        assert query.sort_direction == SortDirection.DESC
        assert query.pagination_mode == PaginationMode.CURSOR
        assert query.cursor is None
        assert query.limit == 50
        assert query.offset == 0

    def test_custom_filters(self) -> None:
        """Query accepts custom filter values."""
        query = KnowledgeQuery(
            source_type="rss",
            source_name="techcrunch",
            limit=100,
            offset=20,
            pagination_mode=PaginationMode.PAGE,
        )

        assert query.source_type == "rss"
        assert query.source_name == "techcrunch"
        assert query.limit == 100
        assert query.offset == 20
        assert query.pagination_mode == PaginationMode.PAGE

    def test_limit_validation(self) -> None:
        """Limit must be between 1 and 500."""
        with pytest.raises(ValidationError):
            KnowledgeQuery(limit=0)

        with pytest.raises(ValidationError):
            KnowledgeQuery(limit=501)

    def test_offset_validation(self) -> None:
        """Offset must be non-negative."""
        with pytest.raises(ValidationError):
            KnowledgeQuery(offset=-1)

    def test_sort_options(self) -> None:
        """Sort field and direction are configurable."""
        query = KnowledgeQuery(
            sort_field=SortField.PUBLISHED_AT,
            sort_direction=SortDirection.ASC,
        )

        assert query.sort_field == SortField.PUBLISHED_AT
        assert query.sort_direction == SortDirection.ASC


# =============================================================================
# Response Models Tests
# =============================================================================


class TestKnowledgeItemSummary:
    """Tests for KnowledgeItemSummary model."""

    def test_basic_summary(self) -> None:
        """Summary contains required fields."""
        summary = KnowledgeItemSummary(
            id="abc-123",
            title="Test Article",
            source_type="rss",
            source_name="techcrunch",
            content_hash="hash123",
        )

        assert summary.id == "abc-123"
        assert summary.title == "Test Article"
        assert summary.topics == []

    def test_summary_with_all_fields(self) -> None:
        """Summary with all optional fields populated."""
        now = datetime.now(timezone.utc)
        summary = KnowledgeItemSummary(
            id="abc-123",
            title="Test",
            source_type="rss",
            source_name="techcrunch",
            published_at=now,
            created_at=now,
            content_hash="hash123",
            topics=["AI", "ML"],
        )

        assert summary.published_at == now
        assert summary.topics == ["AI", "ML"]


class TestKnowledgeListResponse:
    """Tests for KnowledgeListResponse model."""

    def test_empty_response(self) -> None:
        """Empty list response has default values."""
        response = KnowledgeListResponse()

        assert response.items == []
        assert response.total is None
        assert response.page_info.has_next is False

    def test_response_with_items(self) -> None:
        """Response with items and pagination info."""
        items = [
            KnowledgeItemSummary(
                id=f"item-{i}",
                title=f"Item {i}",
                source_type="rss",
                source_name="test",
                content_hash=f"hash-{i}",
            )
            for i in range(5)
        ]

        response = KnowledgeListResponse(
            items=items,
            total=100,
            page_info=PageInfo(
                next_cursor="cursor-123",
                has_next=True,
                has_prev=False,
                total=100,
            ),
        )

        assert len(response.items) == 5
        assert response.total == 100
        assert response.page_info.has_next is True
        assert response.page_info.next_cursor == "cursor-123"


class TestKnowledgeDetailResponse:
    """Tests for KnowledgeDetailResponse model."""

    def test_detail_response(self) -> None:
        """Detail response contains full object info."""
        detail = KnowledgeDetailResponse(
            id="abc-123",
            title="Test Article",
            source_type="rss",
            source_name="techcrunch",
            external_id="guid-456",
            source_url="https://example.com/article",
            content_text="Full content here",
            content_hash="hash123",
            metadata={"summary": "Test summary", "topics": ["AI"]},
            citations=["https://example.com/article"],
        )

        assert detail.id == "abc-123"
        assert detail.metadata["summary"] == "Test summary"
        assert len(detail.citations) == 1


class TestRepositoryStatistics:
    """Tests for RepositoryStatistics model."""

    def test_statistics(self) -> None:
        """Statistics model holds aggregate data."""
        stats = RepositoryStatistics(
            total_items=1000,
            by_source={"rss/techcrunch": 500, "github/repo1": 300},
            by_date_range={"2025-01-01": 50, "2025-01-02": 30},
            last_updated="2025-01-02T10:00:00",
        )

        assert stats.total_items == 1000
        assert stats.by_source["rss/techcrunch"] == 500


class TestSourceHealth:
    """Tests for SourceHealth model."""

    def test_source_health(self) -> None:
        """Source health model holds per-source info."""
        health = SourceHealth(
            source_type="rss",
            source_name="techcrunch",
            total_items=500,
            last_published_at="2025-01-02T10:00:00",
            last_created_at="2025-01-02T10:05:00",
        )

        assert health.total_items == 500
        assert health.source_type == "rss"


# =============================================================================
# Error Contract Tests
# =============================================================================


class TestErrorContract:
    """Tests for typed exception hierarchy."""

    def test_not_found_error(self) -> None:
        """RepositoryNotFoundError includes resource info."""
        error = RepositoryNotFoundError(
            resource_type="knowledge_item",
            resource_id="abc-123",
        )

        assert "knowledge_item" in str(error)
        assert "abc-123" in str(error)

    def test_not_found_error_without_id(self) -> None:
        """RepositoryNotFoundError works without resource_id."""
        error = RepositoryNotFoundError(resource_type="item")
        assert "not found" in str(error)

    def test_unavailable_error(self) -> None:
        """RepositoryUnavailableError has default message."""
        error = RepositoryUnavailableError()
        assert "unavailable" in str(error)

    def test_invalid_query_error(self) -> None:
        """InvalidQueryError accepts custom message."""
        error = InvalidQueryError("limit must be positive")
        assert "limit" in str(error)

    def test_error_hierarchy(self) -> None:
        """All errors inherit from RepositoryError."""
        from app.services.repository.query_models import RepositoryError

        assert issubclass(RepositoryNotFoundError, RepositoryError)
        assert issubclass(RepositoryUnavailableError, RepositoryError)
        assert issubclass(InvalidQueryError, RepositoryError)
