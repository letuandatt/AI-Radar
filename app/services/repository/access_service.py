"""Repository Access Service.

Application Service Layer for INFRA-002 (Web Dashboard) and MCP-001 (Read-Only MCP).
Provides typed, paginated access to the Knowledge Repository.

This is the "Application Service" that MCP adapter and Web Dashboard
will call into, avoiding direct storage access.
"""

from typing import Any

from app.core.logger import get_logger
from app.models.knowledge_object import KnowledgeObject
from app.services.repository.query_models import (
    InvalidQueryError,
    KnowledgeDetailResponse,
    KnowledgeItemSummary,
    KnowledgeListResponse,
    KnowledgeQuery,
    PageInfo,
    PaginationMode,
    RepositoryStatistics,
    SourceHealth,
)
from app.storage.knowledge.sqlite_store import SQLiteKnowledgeStore

logger = get_logger(__name__)


class RepositoryAccessService:
    """Application Service Layer for Knowledge Repository access.

    Provides typed, paginated read operations for external consumers
    (MCP adapter, Web Dashboard, future API layer).

    Args:
        sqlite_store: SQLiteKnowledgeStore instance.
    """

    def __init__(self, sqlite_store: SQLiteKnowledgeStore) -> None:
        self._store = sqlite_store

    # ------------------------------------------------------------------
    # Read Operations
    # ------------------------------------------------------------------

    def get_knowledge_item(self, item_id: str) -> KnowledgeDetailResponse | None:
        """Get a single knowledge item by ID.

        Args:
            item_id: Internal UUID of the knowledge item.

        Returns:
            KnowledgeDetailResponse if found, None otherwise.
        """
        obj = self._store.get_by_id(item_id)
        if obj is None:
            return None

        return self._to_detail_response(obj)

    def list_recent_items(self, limit: int = 50) -> KnowledgeListResponse:
        """List the most recent knowledge items.

        Args:
            limit: Maximum number of items to return.

        Returns:
            KnowledgeListResponse with recent items.
        """
        if limit <= 0 or limit > 500:
            raise InvalidQueryError(f"limit must be between 1 and 500, got {limit}")

        # Fetch limit+1 to determine has_next
        objects = self._store.query_recent(limit=limit + 1)

        has_next = len(objects) > limit
        items_objects = objects[:limit]

        items = [self._to_summary(obj) for obj in items_objects]

        next_cursor = None
        if has_next and items_objects:
            next_cursor = self._to_iso(items_objects[-1].created_at)

        return KnowledgeListResponse(
            items=items,
            total=None,  # Cursor pagination does not provide total
            page_info=PageInfo(
                next_cursor=next_cursor,
                has_next=has_next,
                has_prev=False,
                total=None,
            ),
        )

    def list_items_by_source(
        self,
        source_type: str,
        source_name: str,
        limit: int = 50,
    ) -> KnowledgeListResponse:
        """List knowledge items from a specific source.

        Args:
            source_type: Source type filter.
            source_name: Source name filter.
            limit: Maximum number of items to return.

        Returns:
            KnowledgeListResponse with items from the source.
        """
        if limit <= 0 or limit > 500:
            raise InvalidQueryError(f"limit must be between 1 and 500, got {limit}")

        objects = self._store.query_by_source(
            source_type=source_type,
            source_name=source_name,
            limit=limit + 1,
        )

        has_next = len(objects) > limit
        items_objects = objects[:limit]

        items = [self._to_summary(obj) for obj in items_objects]

        next_cursor = None
        if has_next and items_objects:
            next_cursor = self._to_iso(items_objects[-1].created_at)

        return KnowledgeListResponse(
            items=items,
            total=None,
            page_info=PageInfo(
                next_cursor=next_cursor,
                has_next=has_next,
                has_prev=False,
                total=None,
            ),
        )

    def search_knowledge(self, query: KnowledgeQuery) -> KnowledgeListResponse:
        """Search knowledge items using structured filters and pagination.

        Args:
            query: KnowledgeQuery with filters, sort, and pagination.

        Returns:
            KnowledgeListResponse with matching items.

        Raises:
            InvalidQueryError: If query parameters are invalid.
        """
        if query.limit <= 0 or query.limit > 500:
            raise InvalidQueryError(f"limit must be between 1 and 500, got {query.limit}")

        if query.pagination_mode == PaginationMode.CURSOR:
            return self._search_cursor(query)
        else:
            return self._search_page(query)

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------

    def get_statistics(self) -> RepositoryStatistics:
        """Get aggregate statistics for the knowledge repository.

        Returns:
            RepositoryStatistics with totals and breakdowns.
        """
        stats = self._store.get_statistics()

        return RepositoryStatistics(
            total_items=stats["total_items"],
            by_source=stats["by_source"],
            by_date_range=stats["by_date_range"],
            last_updated=stats["last_updated"],
        )

    def get_source_health(self) -> list[SourceHealth]:
        """Get health status for each knowledge source.

        Returns:
            List of SourceHealth with item counts and timestamps.
        """
        health_data = self._store.get_source_health()

        return [
            SourceHealth(
                source_type=item["source_type"],
                source_name=item["source_name"],
                total_items=item["total_items"],
                last_published_at=item["last_published_at"],
                last_created_at=item["last_created_at"],
            )
            for item in health_data
        ]

    # ------------------------------------------------------------------
    # Private: Cursor-based Pagination
    # ------------------------------------------------------------------

    def _search_cursor(self, query: KnowledgeQuery) -> KnowledgeListResponse:
        """Execute cursor-based pagination search."""
        # Fetch limit+1 to determine has_next
        fetch_limit = query.limit + 1

        objects = self._store.query_by_cursor(
            cursor=query.cursor,
            limit=fetch_limit,
            source_type=query.source_type,
            source_name=query.source_name,
        )

        has_next = len(objects) > query.limit
        items_objects = objects[: query.limit]

        items = [self._to_summary(obj) for obj in items_objects]

        next_cursor = None
        if has_next and items_objects:
            next_cursor = self._to_iso(items_objects[-1].created_at)

        return KnowledgeListResponse(
            items=items,
            total=None,
            page_info=PageInfo(
                next_cursor=next_cursor,
                has_next=has_next,
                has_prev=query.cursor is not None,
                total=None,
            ),
        )

    # ------------------------------------------------------------------
    # Private: Page-based Pagination
    # ------------------------------------------------------------------

    def _search_page(self, query: KnowledgeQuery) -> KnowledgeListResponse:
        """Execute page-based pagination search."""
        objects = self._store.query_by_metadata(
            source_type=query.source_type,
            source_name=query.source_name,
            published_after=query.published_after,
            published_before=query.published_before,
            limit=query.limit,
            offset=query.offset,
        )

        items = [self._to_summary(obj) for obj in objects]

        # For page-based, we need total count
        total = self._store.count()

        has_next = (query.offset + query.limit) < total
        has_prev = query.offset > 0

        return KnowledgeListResponse(
            items=items,
            total=total,
            page_info=PageInfo(
                next_cursor=None,
                has_next=has_next,
                has_prev=has_prev,
                total=total,
            ),
        )

    # ------------------------------------------------------------------
    # Private: Response Converters
    # ------------------------------------------------------------------

    def _to_summary(self, obj: KnowledgeObject) -> KnowledgeItemSummary:
        """Convert KnowledgeObject to KnowledgeItemSummary."""
        return KnowledgeItemSummary(
            id=obj.id,
            title=obj.title,
            source_type=obj.source_type,
            source_name=obj.source_name,
            published_at=obj.published_at,
            created_at=obj.created_at,
            content_hash=obj.content_hash,
            topics=obj.metadata.topics if obj.metadata else [],
        )

    def _to_detail_response(self, obj: KnowledgeObject) -> KnowledgeDetailResponse:
        """Convert KnowledgeObject to KnowledgeDetailResponse."""
        metadata_dict: dict[str, Any] = {}
        if obj.metadata:
            metadata_dict = obj.metadata.model_dump()

        return KnowledgeDetailResponse(
            id=obj.id,
            title=obj.title,
            source_type=obj.source_type,
            source_name=obj.source_name,
            external_id=obj.external_id,
            source_url=obj.source_url,
            content_text=obj.content_text,
            content_hash=obj.content_hash,
            metadata=metadata_dict,
            published_at=obj.published_at,
            created_at=obj.created_at,
            updated_at=obj.updated_at,
            citations=[obj.source_url] if obj.source_url else [],
        )

    @staticmethod
    def _to_iso(value: Any) -> str | None:
        """Convert datetime to ISO string or None."""
        if value is None:
            return None
        if isinstance(value, str):
            return value
        return value.isoformat()  # type: ignore[no-any-return]
