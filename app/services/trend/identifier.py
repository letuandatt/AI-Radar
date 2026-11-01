"""Identify weekly topic, source and entity trend without LLM calls."""

from collections import defaultdict
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import NAMESPACE_URL, uuid5

from app.core.logger import get_logger
from app.services.analysis.models import ObservedKnowledgeItem
from app.services.analysis.topics import source_labels, topic_signals
from app.services.repository.access_service import RepositoryAccessService
from app.services.trend.models import (
    Trend,
    TrendRun,
    TrendSnapshot,
    TrendType,
    WeeklyTrendReport,
    trend_identity,
    week_label,
    week_start,
)

logger = get_logger(__name__)
Signal = tuple[TrendType, str]


class TrendIdentifier:
    """Compute and atomically persist one comparison of completed ISO weeks.

    The public list is filtered by current count; storage retains all candidates,
    including declines to zero. Sync database work must be offloaded with
    asyncio.to_thread when invoked from an async caller. No scheduler is started.
    """

    def __init__(
        self,
        access_service: RepositoryAccessService,
        *,
        min_count: int = 3,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if isinstance(min_count, bool) or not isinstance(min_count, int) or min_count < 1:
            raise ValueError("min_count must be a positive integer")
        self._access = access_service
        self._min_count = min_count
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def identify_trends(self, week: str, baseline_week: str) -> list[Trend]:
        """Persist the full comparison and return current_count >= min_count."""
        return self.get_weekly_trends(week, baseline_week).trends

    def get_weekly_trends(
        self, week: str | None = None, baseline_week: str | None = None
    ) -> WeeklyTrendReport:
        """Default to the last completed UTC week against its preceding week."""
        now = self._clock()
        if now.utcoffset() is None:
            raise ValueError("clock must return a timezone-aware datetime")
        now = now.astimezone(timezone.utc)
        week = week or week_label(week_start(week_label(now)) - timedelta(days=7))
        start = week_start(week)
        baseline_week = baseline_week or week_label(start - timedelta(days=7))
        baseline_start = week_start(baseline_week)
        run = TrendRun(
            week=week,
            baseline_week=baseline_week,
            computed_at=now,
            current_items=0,
            baseline_items=0,
            snapshot_count=0,
            min_count=self._min_count,
        )
        end = start + timedelta(days=7)
        logger.info("Trend identification: week=%s, baseline=%s", week, baseline_week)
        # One repository read gives both cohorts the same view of stored labels.
        items = self._access.list_trend_items(baseline_start, end)
        current = [item for item in items if start <= item.first_observed_at < end]
        baseline_end = baseline_start + timedelta(days=7)
        baseline = [
            item for item in items if baseline_start <= item.first_observed_at < baseline_end
        ]
        trends = self._compare(current, baseline)
        run = run.model_copy(
            update={
                "current_items": len({item.knowledge_id for item in current}),
                "baseline_items": len({item.knowledge_id for item in baseline}),
                "snapshot_count": len(trends),
            }
        )
        snapshots = [
            TrendSnapshot(
                **trend.model_dump(),
                week=week,
                baseline_week=baseline_week,
                computed_at=now,
                snapshot_id=str(uuid5(NAMESPACE_URL, f"{trend.trend_id}:{week}")),
            )
            for trend in trends
        ]
        self._access.save_trend_snapshots(snapshots, run=run)
        selected = [trend for trend in trends if trend.current_count >= self._min_count]
        logger.info(
            "Trend snapshots saved: %d; returned: %d; observed items current=%d, baseline=%d",
            len(snapshots),
            len(selected),
            run.current_items,
            run.baseline_items,
        )
        return WeeklyTrendReport(**run.model_dump(), trends=selected)

    @staticmethod
    def _signals(items: list[ObservedKnowledgeItem]) -> dict[Signal, set[str]]:
        groups: dict[Signal, set[str]] = defaultdict(set)
        for item in items:
            signals: set[Signal] = {("source", source_labels([item])[0])}
            for key in topic_signals(item):
                kind, name = key.split(":", 1)
                signals.add(("topic", name) if kind == "theme" else ("entity", key))
            for signal in signals:
                groups[signal].add(item.knowledge_id)
        return groups

    def _compare(
        self, current: list[ObservedKnowledgeItem], baseline: list[ObservedKnowledgeItem]
    ) -> list[Trend]:
        current_groups, baseline_groups = self._signals(current), self._signals(baseline)
        candidates = sorted(current_groups.keys() | baseline_groups.keys())
        trends = []
        for kind in ("topic", "source", "entity"):
            keys = [key for key in candidates if key[0] == kind]
            counts = {key: len(current_groups.get(key, set())) for key in keys}
            previous = {key: len(baseline_groups.get(key, set())) for key in keys}
            max_count = max(counts.values(), default=0)
            for key in keys:
                count, old = counts[key], previous[key]
                delta = (count - old) / old * 100 if old else None
                comparison: Literal["comparable", "new", "baseline_empty"] = (
                    "comparable" if old else "new" if baseline else "baseline_empty"
                )
                normalized_delta = (
                    min(1.0, max(-1.0, delta / 100))
                    if delta is not None
                    else 1.0
                    if comparison == "new"
                    else 0.0
                )
                rank = 1 + sum(value > count for value in counts.values())
                baseline_rank = 1 + sum(value > old for value in previous.values())
                rank_change = baseline_rank - rank if baseline else 0
                rank_bonus = rank_change / max(len(keys) - 1, 1)
                normalized_count = count / max_count if max_count else 0.0
                trends.append(
                    Trend(
                        trend_id=trend_identity(key[0], key[1]),
                        type=key[0],
                        name=key[1],
                        current_count=count,
                        baseline_count=old,
                        delta_percent=delta,
                        comparison=comparison,
                        rank_change=rank_change,
                        normalized_delta=normalized_delta,
                        normalized_count=normalized_count,
                        rank_bonus=rank_bonus,
                        trend_score=0.6 * normalized_delta
                        + 0.3 * normalized_count
                        + 0.1 * rank_bonus,
                        sample_knowledge_ids=sorted(
                            current_groups.get(key, set()) | baseline_groups.get(key, set())
                        )[:5],
                    )
                )
        return sorted(trends, key=lambda trend: (-trend.trend_score, trend.type, trend.name))
