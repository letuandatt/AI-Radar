"""Repository Access Service.

Application Service Layer for INFRA-002 (Web Dashboard) and MCP-001 (Read-Only MCP).
Provides typed, paginated access to the Knowledge Repository.

This is the "Application Service" that MCP adapter and Web Dashboard
will call into, avoiding direct storage access.
"""

import json
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

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

if TYPE_CHECKING:
    from app.services.analysis.models import (
        AnalyzedKnowledgeItem,
        ContentAnalysisResult,
        CrossSourceGroup,
        DiscoveredPattern,
        ObservedKnowledgeItem,
        PatternSnapshot,
    )
    from app.services.importance.models import ImportanceInputs, ImportanceScore
    from app.services.intelligence.models import Insight, InsightRun
    from app.services.trend.models import TrendRun, TrendSnapshot

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
    # Trend Identification
    # ------------------------------------------------------------------

    def load_intelligence_inputs(self, date: str) -> dict[str, Any]:
        """Load a bounded daily cohort and current saved S19/S21 prerequisites."""
        from app.services.intelligence.models import day_start

        start = day_start(date)
        return self._store.load_intelligence_inputs(
            start.isoformat(), (start + timedelta(days=1)).isoformat()
        )

    def save_insights(self, insights: list["Insight"], *, run: "InsightRun") -> None:
        """Validate the complete replacement, including an explicit empty run."""
        from app.services.intelligence.models import Insight, InsightRun

        run = InsightRun.model_validate(run.model_dump())
        rows = [Insight.model_validate(row.model_dump()) for row in insights]
        if run.insight_count != len(rows) or len({row.insight_id for row in rows}) != len(rows):
            raise ValueError("Insight count/identities do not match run")
        if any(
            row.report_date != run.report_date or row.generated_at != run.generated_at
            for row in rows
        ):
            raise ValueError("Insight does not match run metadata")
        self._store.save_insights(
            [row.model_dump(mode="json") for row in rows], run.model_dump(mode="json")
        )

    def read_insight_report(
        self, date: str | None = None
    ) -> tuple["InsightRun | None", list["Insight"]]:
        """Read one coherent report; None selects the newest successful report day."""
        from app.services.intelligence.models import Insight, InsightRun, day_start

        if date is not None:
            day_start(date)
        data = self._store.read_insight_report(date)
        run = InsightRun.model_validate(data["run"]) if data["run"] is not None else None
        rows = [Insight.model_validate(row) for row in data["insights"]]
        if (run is None and rows) or (
            run is not None
            and (
                run.insight_count != len(rows)
                or any(
                    row.report_date != run.report_date or row.generated_at != run.generated_at
                    for row in rows
                )
            )
        ):
            raise ValueError("Inconsistent insight report")
        return run, rows

    def list_insights(self, date: str, insight_type: str | None = None) -> list["Insight"]:
        """List saved insights; use read_insight_report to distinguish empty/missing."""
        if insight_type is not None and insight_type not in {
            "trend",
            "pattern",
            "connection",
            "warning",
        }:
            raise ValueError("Unknown insight type")
        _, rows = self.read_insight_report(date)
        return [row for row in rows if insight_type is None or row.insight_type == insight_type]

    def load_importance_inputs(
        self, knowledge_ids: list[str], start: datetime, end: datetime, week: str
    ) -> "ImportanceInputs":
        """Read scoring evidence once, keeping missing and empty history explicit."""
        from app.services.importance.models import ImportanceInputs
        from app.services.trend.models import week_start

        if start.utcoffset() is None or end.utcoffset() is None or start >= end:
            raise ValueError("Expected an ordered timezone-aware scoring interval")
        if week_start(week) + timedelta(days=7) > end:
            raise ValueError("Trend context must be a completed UTC week")
        data = self._store.load_importance_inputs(
            knowledge_ids, start.isoformat(), end.isoformat(), week
        )
        wanted = set(knowledge_ids)
        parsed = []
        for row in data["analyses"]:
            value = dict(row)
            at = datetime.fromisoformat(value["analyzed_at"])
            if value["knowledge_id"] not in wanted and not start <= at <= end:
                continue
            for key in ("themes", "entities", "key_claims"):
                value[key] = json.loads(value.pop(f"{key}_json"))
            parsed.append(value)
        data["analyses"] = parsed
        result = ImportanceInputs.model_validate(data)
        run, trends = result.trend_run, result.trends
        if run is None:
            if trends:
                raise ValueError("Trend snapshots have no run metadata")
        elif (
            run.week != week
            or run.computed_at > end
            or run.snapshot_count != len(trends)
            or len({row.trend_id for row in trends}) != len(trends)
            or any(
                row.week != week
                or row.computed_at != run.computed_at
                or row.baseline_week != run.baseline_week
                or row.current_count > run.current_items
                or row.baseline_count > run.baseline_items
                for row in trends
            )
        ):
            raise ValueError("Inconsistent or future trend context")
        return result

    def save_importance_scores(self, scores: list["ImportanceScore"]) -> None:
        """Validate every score before issuing one atomic store operation."""
        from app.services.importance.models import ImportanceScore

        validated = [ImportanceScore.model_validate(score.model_dump()) for score in scores]
        if len({score.knowledge_id for score in validated}) != len(validated):
            raise ValueError("Duplicate knowledge_id in importance batch")
        self._store.save_importance_scores([score.model_dump(mode="json") for score in validated])

    def get_importance_score(self, knowledge_id: str) -> "ImportanceScore | None":
        """Read a saved score; None means no score for a live knowledge item."""
        from app.services.importance.models import ImportanceScore

        row = self._store.get_importance_score(knowledge_id)
        return ImportanceScore.model_validate(row) if row is not None else None

    def list_trend_items(self, start: datetime, end: datetime) -> list["ObservedKnowledgeItem"]:
        """Read live analyzed items in [start, end), anchored to first persistence."""
        from app.services.analysis.models import ObservedKnowledgeItem

        if start.utcoffset() is None or end.utcoffset() is None or start >= end:
            raise ValueError("Expected an ordered timezone-aware interval")
        rows = self._store.query_trend_items(
            start.astimezone(timezone.utc).isoformat(), end.astimezone(timezone.utc).isoformat()
        )
        items = []
        for row in rows:
            data = dict(row)
            for field in ("themes", "entities", "key_claims"):
                data[field] = json.loads(data.pop(f"{field}_json"))
            items.append(ObservedKnowledgeItem.model_validate(data))
        return items

    def save_trend_snapshots(self, snapshots: list["TrendSnapshot"], *, run: "TrendRun") -> None:
        """Validate a full weekly snapshot, then replace it and its run atomically."""
        from app.services.trend.models import TrendRun, TrendSnapshot

        run = TrendRun.model_validate(run.model_dump())
        snapshots = [TrendSnapshot.model_validate(item.model_dump()) for item in snapshots]
        if run.snapshot_count != len(snapshots):
            raise ValueError("snapshot_count must match the complete candidate list")
        if len({item.trend_id for item in snapshots}) != len(snapshots):
            raise ValueError("Duplicate trend identity in one run")
        for item in snapshots:
            if (
                item.week != run.week
                or item.baseline_week != run.baseline_week
                or item.computed_at != run.computed_at
                or item.current_count > run.current_items
                or item.baseline_count > run.baseline_items
                or (item.comparison == "baseline_empty") != (run.baseline_items == 0)
            ):
                raise ValueError("Snapshot does not match run metadata")
        self._store.save_trend_snapshots(
            [item.model_dump(mode="json") for item in snapshots], run.model_dump(mode="json")
        )

    def list_trend_snapshots(self, week: str) -> list["TrendSnapshot"]:
        """Return ALL weekly candidates, including below-threshold declines."""
        from app.services.trend.models import TrendSnapshot, week_start

        week_start(week)
        return [TrendSnapshot.model_validate(row) for row in self._store.list_trend_snapshots(week)]

    def get_trend_run(self, week: str) -> "TrendRun | None":
        """Return run metadata, or None when this week has never been computed."""
        from app.services.trend.models import TrendRun, week_start

        week_start(week)
        row = self._store.get_trend_run(week)
        return TrendRun.model_validate(row) if row is not None else None

    # ------------------------------------------------------------------
    # Content Analysis Management
    # ------------------------------------------------------------------

    def list_items_in_window(self, days: int = 7) -> list["AnalyzedKnowledgeItem"]:
        """Read analyses from [now - days, now], joined to live source identities.

        UTC analysis timestamps define the window, not publication timestamps.
        Capture now once so both bounds describe the same read.
        """
        from app.services.analysis.models import AnalyzedKnowledgeItem

        if isinstance(days, bool) or not isinstance(days, int) or days <= 0:
            raise ValueError("days must be a positive integer")
        end = datetime.now(timezone.utc)
        try:
            start = end - timedelta(days=days)
        except OverflowError as exc:
            raise ValueError("days exceeds the supported datetime range") from exc
        rows = self._store.query_analyses_in_window(start.isoformat(), end.isoformat())
        return [
            AnalyzedKnowledgeItem(
                knowledge_id=row["knowledge_id"],
                analyzed_at=row["analyzed_at"],
                source_type=row["source_type"],
                source_name=row["source_name"],
                themes=json.loads(row["themes_json"]),
                entities=json.loads(row["entities_json"]),
                sentiment=row["sentiment"],
                key_claims=json.loads(row["key_claims_json"]),
                technical_depth=row["technical_depth"],
                confidence=row["confidence"],
            )
            for row in rows
        ]

    def list_pattern_items(self, start: datetime, end: datetime) -> list["ObservedKnowledgeItem"]:
        """Read current analysis labels anchored to first persistence in (start, end]."""
        from app.services.analysis.models import ObservedKnowledgeItem

        if start.utcoffset() is None or end.utcoffset() is None or start >= end:
            raise ValueError("Expected an ordered timezone-aware interval")
        rows = self._store.query_pattern_items(
            start.astimezone(timezone.utc).isoformat(), end.astimezone(timezone.utc).isoformat()
        )
        items = []
        for row in rows:
            data = dict(row)
            for field in ("themes", "entities", "key_claims"):
                data[field] = json.loads(data.pop(f"{field}_json"))
            items.append(ObservedKnowledgeItem.model_validate(data))
        return items

    def save_discovered_patterns(
        self, patterns: list["DiscoveredPattern"], observed_at: datetime
    ) -> list["DiscoveredPattern"]:
        """Save one run and return records with their preserved first_detected values."""
        from app.services.analysis.models import DiscoveredPattern

        if observed_at.utcoffset() is None:
            raise ValueError("observed_at must be timezone-aware")
        ids = [pattern.pattern_id for pattern in patterns]
        if len(ids) != len(set(ids)):
            raise ValueError("pattern IDs must be unique within a run")
        records = self._store.save_pattern_records(
            [pattern.model_dump(mode="json") for pattern in patterns],
            observed_at.astimezone(timezone.utc).isoformat(),
        )
        return [DiscoveredPattern.model_validate(record) for record in records]

    def get_pattern_history(self, pattern_id: str) -> list["PatternSnapshot"]:
        """Read snapshots through the repository gateway, oldest first."""
        from app.services.analysis.models import PatternSnapshot

        return [
            PatternSnapshot.model_validate(record)
            for record in self._store.query_pattern_history(pattern_id)
        ]

    def save_cross_source_groups(
        self, groups: list["CrossSourceGroup"], time_window_days: int = 7
    ) -> None:
        """Replace all persisted groups for one window in a single transaction."""
        if (
            isinstance(time_window_days, bool)
            or not isinstance(time_window_days, int)
            or time_window_days <= 0
        ):
            raise ValueError("time_window_days must be a positive integer")
        rows = [
            {
                "group_id": group.group_id,
                "topic": group.topic,
                "knowledge_ids_json": json.dumps(group.knowledge_ids),
                "source_count": group.source_count,
                "sources_json": json.dumps(group.sources),
                "first_seen": group.first_seen.isoformat(),
                "last_seen": group.last_seen.isoformat(),
                "coverage_score": group.coverage_score,
            }
            for group in groups
        ]
        self._store.replace_cross_source_groups(time_window_days, rows)

    def list_unanalyzed_items(self, limit: int = 50) -> list[KnowledgeObject]:
        """List KnowledgeObjects that do not have a content analysis yet.

        Args:
            limit: Maximum number of items to return.

        Returns:
            List of unanalyzed KnowledgeObjects.
        """
        return self._store.query_unanalyzed(limit)

    def save_content_analysis(self, result: "ContentAnalysisResult") -> None:
        """Save a content analysis result.

        Args:
            result: The analysis result to persist.
        """
        import json
        import uuid

        analysis_id = str(uuid.uuid4())

        self._store.save_analysis(
            analysis_id=analysis_id,
            knowledge_id=result.knowledge_id,
            analyzed_at=result.analyzed_at.isoformat(),
            themes_json=json.dumps(result.themes),
            entities_json=json.dumps(result.entities.model_dump()),
            sentiment=result.sentiment,
            key_claims_json=json.dumps(result.key_claims),
            technical_depth=result.technical_depth,
            confidence=result.confidence,
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
