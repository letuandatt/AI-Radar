"""Unit tests for RepositoryAccessService."""

import threading
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from app.core.utils import compute_text_hash
from app.models.knowledge_object import KnowledgeObject
from app.models.metadata import ExtractionResult
from app.services.repository.access_service import RepositoryAccessService
from app.services.repository.query_models import (
    InvalidQueryError,
    KnowledgeQuery,
    PaginationMode,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_sqlite_store():
    """Create a mock SQLiteKnowledgeStore."""
    store = MagicMock()
    store.count.return_value = 0
    store.get_all.return_value = []
    store.get_by_id.return_value = None
    store.query_recent.return_value = []
    store.query_by_source.return_value = []
    store.query_by_metadata.return_value = []
    store.query_by_cursor.return_value = []
    store.get_statistics.return_value = {
        "total_items": 0,
        "by_source": {},
        "by_date_range": {},
        "last_updated": None,
    }
    store.get_source_health.return_value = []
    return store


@pytest.fixture
def service(mock_sqlite_store):
    """Create RepositoryAccessService with mock store."""
    return RepositoryAccessService(sqlite_store=mock_sqlite_store)


def _make_ko(
    obj_id: str = "ko_001",
    content: str = "Test content",
    source_type: str = "rss",
    source_name: str = "test_source",
    title: str = "Test Title",
    published_at: datetime | None = None,
    created_at: datetime | None = None,
) -> KnowledgeObject:
    """Helper to create a KnowledgeObject."""
    metadata = ExtractionResult(
        summary="Summary",
        topics=["AI", "ML"],
        entities=["OpenAI"],
        relevance_score=0.9,
    )
    ko = KnowledgeObject(
        source_type=source_type,
        source_name=source_name,
        external_id=f"ext_{obj_id}",
        source_url=f"https://example.com/{obj_id}",
        content_hash=compute_text_hash(content),
        fetched_at=datetime(2025, 1, 2, tzinfo=timezone.utc),
        published_at=published_at or datetime(2025, 1, 1, tzinfo=timezone.utc),
        title=title,
        content_text=content,
        metadata=metadata,
    )
    ko.id = obj_id
    if created_at:
        ko.created_at = created_at
    return ko


# =============================================================================
# get_knowledge_item Tests
# =============================================================================


class TestGetKnowledgeItem:
    """Tests for get_knowledge_item method."""

    def test_get_existing_item(self, service, mock_sqlite_store) -> None:
        """get_knowledge_item returns detail for existing item."""
        ko = _make_ko()
        mock_sqlite_store.get_by_id.return_value = ko

        result = service.get_knowledge_item("ko_001")

        assert result is not None
        assert result.id == "ko_001"
        assert result.title == "Test Title"
        assert result.content_text == "Test content"
        assert result.metadata["summary"] == "Summary"
        assert result.metadata["topics"] == ["AI", "ML"]

    def test_get_nonexistent_item(self, service, mock_sqlite_store) -> None:
        """get_knowledge_item returns None for missing item."""
        mock_sqlite_store.get_by_id.return_value = None

        result = service.get_knowledge_item("nonexistent")

        assert result is None

    def test_get_item_citations(self, service, mock_sqlite_store) -> None:
        """get_knowledge_item includes source_url in citations."""
        ko = _make_ko()
        mock_sqlite_store.get_by_id.return_value = ko

        result = service.get_knowledge_item("ko_001")

        assert result is not None
        assert len(result.citations) == 1
        assert result.citations[0] == "https://example.com/ko_001"


# =============================================================================
# list_recent_items Tests
# =============================================================================


class TestListRecentItems:
    """Tests for list_recent_items method."""

    def test_list_recent_returns_items(self, service, mock_sqlite_store) -> None:
        """list_recent_items returns recent items."""
        objects = [_make_ko(f"ko_{i}") for i in range(5)]
        mock_sqlite_store.query_recent.return_value = objects

        result = service.list_recent_items(limit=10)

        assert len(result.items) == 5
        assert result.page_info.has_next is False

    def test_list_recent_has_next(self, service, mock_sqlite_store) -> None:
        """list_recent_items sets has_next when more items exist."""
        # Return limit+1 items to indicate has_next
        objects = [_make_ko(f"ko_{i}") for i in range(6)]
        mock_sqlite_store.query_recent.return_value = objects

        result = service.list_recent_items(limit=5)

        assert len(result.items) == 5
        assert result.page_info.has_next is True
        assert result.page_info.next_cursor is not None

    def test_list_recent_empty(self, service, mock_sqlite_store) -> None:
        """list_recent_items returns empty list when no items."""
        mock_sqlite_store.query_recent.return_value = []

        result = service.list_recent_items()

        assert len(result.items) == 0
        assert result.page_info.has_next is False

    def test_list_recent_invalid_limit(self, service) -> None:
        """list_recent_items raises InvalidQueryError for invalid limit."""
        with pytest.raises(InvalidQueryError):
            service.list_recent_items(limit=0)

        with pytest.raises(InvalidQueryError):
            service.list_recent_items(limit=501)


# =============================================================================
# list_items_by_source Tests
# =============================================================================


class TestListItemsBySource:
    """Tests for list_items_by_source method."""

    def test_list_by_source(self, service, mock_sqlite_store) -> None:
        """list_items_by_source returns items from specific source."""
        objects = [
            _make_ko("ko_1", source_type="rss", source_name="cnn"),
            _make_ko("ko_2", source_type="rss", source_name="cnn"),
        ]
        mock_sqlite_store.query_by_source.return_value = objects

        result = service.list_items_by_source("rss", "cnn", limit=10)

        assert len(result.items) == 2
        mock_sqlite_store.query_by_source.assert_called_once()


# =============================================================================
# search_knowledge Tests
# =============================================================================


class TestSearchKnowledge:
    """Tests for search_knowledge method."""

    def test_search_cursor_pagination(self, service, mock_sqlite_store) -> None:
        """search_knowledge with cursor-based pagination."""
        objects = [_make_ko(f"ko_{i}") for i in range(3)]
        mock_sqlite_store.query_by_cursor.return_value = objects

        query = KnowledgeQuery(
            pagination_mode=PaginationMode.CURSOR,
            limit=10,
        )

        result = service.search_knowledge(query)

        assert len(result.items) == 3
        assert result.page_info.has_next is False
        mock_sqlite_store.query_by_cursor.assert_called_once()

    def test_search_cursor_has_next(self, service, mock_sqlite_store) -> None:
        """search_knowledge cursor pagination detects has_next."""
        # Return limit+1 items
        objects = [_make_ko(f"ko_{i}") for i in range(6)]
        mock_sqlite_store.query_by_cursor.return_value = objects

        query = KnowledgeQuery(
            pagination_mode=PaginationMode.CURSOR,
            limit=5,
        )

        result = service.search_knowledge(query)

        assert len(result.items) == 5
        assert result.page_info.has_next is True
        assert result.page_info.next_cursor is not None

    def test_search_cursor_no_duplicates(self, service, mock_sqlite_store) -> None:
        """Cursor-based pagination does not duplicate items across pages."""
        now = datetime.now(timezone.utc)

        # Page 1: 5 items
        page1_objects = [
            _make_ko(f"ko_{i}", created_at=now - timedelta(minutes=i)) for i in range(5)
        ]
        # Page 2: next 5 items (different IDs)
        page2_objects = [
            _make_ko(f"ko_{i + 5}", created_at=now - timedelta(minutes=i + 5)) for i in range(5)
        ]

        mock_sqlite_store.query_by_cursor.side_effect = [
            page1_objects,
            page2_objects,
        ]

        query1 = KnowledgeQuery(
            pagination_mode=PaginationMode.CURSOR,
            limit=5,
        )
        result1 = service.search_knowledge(query1)

        # Get cursor from page 1
        cursor = result1.page_info.next_cursor

        query2 = KnowledgeQuery(
            pagination_mode=PaginationMode.CURSOR,
            limit=5,
            cursor=cursor,
        )
        result2 = service.search_knowledge(query2)

        # Verify no duplicate IDs
        page1_ids = {item.id for item in result1.items}
        page2_ids = {item.id for item in result2.items}
        assert page1_ids.isdisjoint(page2_ids)

    def test_search_page_pagination(self, service, mock_sqlite_store) -> None:
        """search_knowledge with page-based pagination."""
        objects = [_make_ko(f"ko_{i}") for i in range(10)]
        mock_sqlite_store.query_by_metadata.return_value = objects
        mock_sqlite_store.count.return_value = 25

        query = KnowledgeQuery(
            pagination_mode=PaginationMode.PAGE,
            limit=10,
            offset=0,
        )

        result = service.search_knowledge(query)

        assert len(result.items) == 10
        assert result.total == 25
        assert result.page_info.has_next is True
        assert result.page_info.has_prev is False

    def test_search_page_offset(self, service, mock_sqlite_store) -> None:
        """Page-based pagination respects offset."""
        objects = [_make_ko(f"ko_{i}") for i in range(10, 20)]
        mock_sqlite_store.query_by_metadata.return_value = objects
        mock_sqlite_store.count.return_value = 50

        query = KnowledgeQuery(
            pagination_mode=PaginationMode.PAGE,
            limit=10,
            offset=10,
        )

        result = service.search_knowledge(query)

        assert result.page_info.has_prev is True
        assert result.page_info.has_next is True

    def test_search_invalid_limit_pydantic(self, service) -> None:
        """KnowledgeQuery rejects invalid limit at model level (Pydantic)."""
        with pytest.raises(ValidationError):
            KnowledgeQuery(limit=0)

        with pytest.raises(ValidationError):
            KnowledgeQuery(limit=501)

        with pytest.raises(ValidationError):
            KnowledgeQuery(offset=-1)

    def test_search_invalid_limit_service(self, service, mock_sqlite_store) -> None:
        """search_knowledge raises InvalidQueryError for edge cases
        that bypass Pydantic validation."""
        mock_sqlite_store.query_by_cursor.return_value = []
        mock_sqlite_store.query_by_metadata.return_value = []
        mock_sqlite_store.count.return_value = 0

        # Simulate a query that somehow has invalid limit
        # (e.g., constructed via model_construct which skips validation)
        query = KnowledgeQuery.model_construct(limit=0)

        with pytest.raises(InvalidQueryError):
            service.search_knowledge(query)


# =============================================================================
# Statistics Tests
# =============================================================================


class TestStatistics:
    """Tests for get_statistics and get_source_health methods."""

    def test_get_statistics(self, service, mock_sqlite_store) -> None:
        """get_statistics returns aggregate data."""
        mock_sqlite_store.get_statistics.return_value = {
            "total_items": 1000,
            "by_source": {"rss/cnn": 500, "github/repo1": 300},
            "by_date_range": {"2025-01-01": 50},
            "last_updated": "2025-01-02T10:00:00",
        }

        result = service.get_statistics()

        assert result.total_items == 1000
        assert result.by_source["rss/cnn"] == 500
        assert result.last_updated == "2025-01-02T10:00:00"

    def test_get_source_health(self, service, mock_sqlite_store) -> None:
        """get_source_health returns per-source info."""
        mock_sqlite_store.get_source_health.return_value = [
            {
                "source_type": "rss",
                "source_name": "cnn",
                "total_items": 500,
                "last_published_at": "2025-01-02T10:00:00",
                "last_created_at": "2025-01-02T10:05:00",
            },
        ]

        result = service.get_source_health()

        assert len(result) == 1
        assert result[0].source_type == "rss"
        assert result[0].total_items == 500


# =============================================================================
# Concurrency Tests
# =============================================================================


class TestConcurrency:
    """Tests for concurrent read operations."""

    def test_concurrent_reads(self, service, mock_sqlite_store) -> None:
        """Multiple simultaneous reads do not cause errors."""
        objects = [_make_ko(f"ko_{i}") for i in range(10)]
        mock_sqlite_store.query_recent.return_value = objects
        mock_sqlite_store.count.return_value = 10

        errors = []

        def read_worker():
            try:
                service.list_recent_items(limit=5)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=read_worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0

    def test_concurrent_reads_and_statistics(self, service, mock_sqlite_store) -> None:
        """Simultaneous reads and statistics calls work correctly."""
        mock_sqlite_store.query_recent.return_value = [_make_ko()]
        mock_sqlite_store.get_statistics.return_value = {
            "total_items": 1,
            "by_source": {},
            "by_date_range": {},
            "last_updated": None,
        }

        errors = []

        def read_worker():
            try:
                service.list_recent_items(limit=5)
            except Exception as e:
                errors.append(e)

        def stats_worker():
            try:
                service.get_statistics()
            except Exception as e:
                errors.append(e)

        threads = []
        for i in range(5):
            threads.append(threading.Thread(target=read_worker))
            threads.append(threading.Thread(target=stats_worker))

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
