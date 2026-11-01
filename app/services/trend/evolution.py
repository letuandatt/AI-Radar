"""Deterministic evolution over persisted weekly trend snapshots."""

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from statistics import fmean, pstdev
from typing import Literal

from app.core.logger import get_logger
from app.services.repository.access_service import RepositoryAccessService
from app.services.trend.models import (
    TrendEvolution,
    TrendRun,
    TrendSnapshot,
    WeeklyCount,
    week_label,
    week_start,
)

logger = get_logger(__name__)
History = list[tuple[str, TrendRun | None, dict[str, TrendSnapshot]]]


class TrendEvolutionAnalyzer:
    """Read saved counts without recomputing or modifying identification runs.

    Public sync methods are called by the local evolution runner; async callers
    must offload the complete call with asyncio.to_thread. No LLM is required.
    """

    def __init__(
        self,
        access_service: RepositoryAccessService,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._access = access_service
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def analyze_evolution(
        self, trend_id: str, weeks: int = 8, *, end_week: str | None = None
    ) -> TrendEvolution:
        """Analyze one trend; raise LookupError if absent from the requested window."""
        history = self._load_history(weeks, end_week)
        for _, _, snapshots in history:
            if trend_id in snapshots:
                return self._analyze(snapshots[trend_id], history)
        raise LookupError(f"No snapshots for trend {trend_id!r} in the requested window")

    def analyze_all_trends(
        self, weeks: int = 8, *, end_week: str | None = None
    ) -> list[TrendEvolution]:
        """Analyze the union of candidates, including disappearing signals.

        Load each week once for the batch, rather than once per trend. Results
        are ordered by type/name/identity, not ranked by evolution or score.
        """
        history = self._load_history(weeks, end_week)
        candidates = {key: row for _, _, snapshots in history for key, row in snapshots.items()}
        results = [self._analyze(row, history) for row in candidates.values()]
        logger.info("Trend evolution complete: %d trends over %d weeks", len(results), weeks)
        return sorted(results, key=lambda result: (result.type, result.name, result.trend_id))

    def _load_history(self, weeks: int, end_week: str | None) -> History:
        if isinstance(weeks, bool) or not isinstance(weeks, int) or weeks < 1:
            raise ValueError("weeks must be a positive integer")
        now = self._clock()
        if now.utcoffset() is None:
            raise ValueError("clock must return a timezone-aware datetime")
        this_week = week_start(week_label(now))
        end = week_start(end_week) if end_week is not None else this_week - timedelta(days=7)
        if end >= this_week:
            raise ValueError("end_week must be a completed UTC week")
        try:
            start = end - timedelta(weeks=weeks - 1)
        except OverflowError as error:
            raise ValueError("weeks exceeds the supported datetime range") from error
        labels = [week_label(start + timedelta(weeks=index)) for index in range(weeks)]
        logger.info("Reading trend history: %s through %s", labels[0], labels[-1])
        history: History = []
        for label in labels:
            run = self._access.get_trend_run(label)
            if run is None:
                history.append((label, None, {}))
                continue
            rows = self._access.list_trend_snapshots(label)
            # Separate public reads must not combine metadata and a newer rerun.
            if self._access.get_trend_run(label) != run:
                raise RuntimeError(f"Trend run changed while reading {label}; retry evolution")
            snapshots = {row.trend_id: row for row in rows}
            if (
                run.week != label
                or run.snapshot_count != len(rows)
                or len(snapshots) != len(rows)
                or any(
                    row.week != label
                    or row.computed_at != run.computed_at
                    or row.baseline_week != run.baseline_week
                    or row.current_count > run.current_items
                    for row in rows
                )
            ):
                raise ValueError(f"Inconsistent trend snapshots for {label}")
            history.append((label, run, snapshots))
        return history

    @staticmethod
    def _analyze(candidate: TrendSnapshot, history: History) -> TrendEvolution:
        points = []
        for label, run, snapshots in history:
            if run is None:
                points.append(WeeklyCount(week=label, count=None, status="missing_run"))
            elif run.current_items == 0:
                points.append(WeeklyCount(week=label, count=0, status="empty_run"))
            else:
                row = snapshots.get(candidate.trend_id)
                points.append(
                    WeeklyCount(
                        week=label, count=row.current_count if row else 0, status="observed"
                    )
                )
        observed = sum(point.status == "observed" for point in points)
        pattern: Literal["growing", "stable", "declining", "volatile"] | None = None
        volatility = None
        status: Literal["classified", "insufficient_history", "no_activity", "unclassified"] = (
            "insufficient_history"
        )
        if observed == len(points) and observed >= 3:
            counts = [point.count for point in points if point.count is not None]
            mean = fmean(counts)
            volatility = pstdev(counts) / mean if mean else 0.0
            pairs = list(zip(counts, counts[1:]))
            if not mean:
                status = "no_activity"
            else:
                status = "classified"
                # Direction has precedence over dispersion; zero has no % growth.
                if all(old > 0 and new * 10 > old * 11 for old, new in pairs):
                    pattern = "growing"
                elif all(new < old for old, new in pairs):
                    pattern = "declining"
                elif volatility < 0.2:
                    pattern = "stable"
                elif volatility > 0.5:
                    pattern = "volatile"
                else:
                    status = "unclassified"
        return TrendEvolution(
            trend_id=candidate.trend_id,
            type=candidate.type,
            name=candidate.name,
            weekly_counts=points,
            observed_weeks=observed,
            pattern=pattern,
            volatility=volatility,
            status=status,
        )
