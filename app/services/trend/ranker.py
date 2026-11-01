"""Rank saved weekly trends and render a deterministic Markdown summary."""

import html
import re
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from app.core.logger import get_logger
from app.services.repository.access_service import RepositoryAccessService
from app.services.trend.evolution import TrendEvolutionAnalyzer
from app.services.trend.models import (
    RankedTrend,
    Trend,
    TrendRanking,
    TrendRun,
    TrendSnapshot,
    TrendType,
    week_start,
)

logger = get_logger(__name__)
KINDS: tuple[TrendType, ...] = ("topic", "source", "entity")


class TrendRanker:
    """Read-only ranking; sync callers in async contexts must use asyncio.to_thread.

    The local ranking runner calls this service directly. Evolution is loaded
    once per batch and anchored to the target week, including historical runs.
    """

    def __init__(
        self,
        access_service: RepositoryAccessService,
        *,
        evolution_weeks: int = 8,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if (
            isinstance(evolution_weeks, bool)
            or not isinstance(evolution_weeks, int)
            or evolution_weeks < 1
        ):
            raise ValueError("evolution_weeks must be a positive integer")
        self._access = access_service
        self._weeks = evolution_weeks
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def rank_trends(self, week: str) -> TrendRanking:
        """Rank a completed week; missing runs raise LookupError, empty runs remain explicit."""
        start = week_start(week)
        now = self._clock()
        if now.utcoffset() is None:
            raise ValueError("clock must return a timezone-aware datetime")
        if start + timedelta(days=7) > now:
            raise ValueError("week must be a completed UTC week")
        # Validate history bounds before any repository reads, including empty runs.
        try:
            start - timedelta(weeks=self._weeks - 1)
        except OverflowError as error:
            raise ValueError("evolution_weeks exceeds the supported datetime range") from error
        run = self._access.get_trend_run(week)
        if run is None:
            raise LookupError(f"No identification run for {week}; run identification first")
        snapshots = self._access.list_trend_snapshots(week)
        if (
            run.week != week
            or len(snapshots) != run.snapshot_count
            or len({row.trend_id for row in snapshots}) != len(snapshots)
            or any(
                row.week != week
                or row.baseline_week != run.baseline_week
                or row.computed_at != run.computed_at
                or row.current_count > run.current_items
                or row.baseline_count > run.baseline_items
                or (row.comparison == "baseline_empty") != (run.baseline_items == 0)
                for row in snapshots
            )
        ):
            raise ValueError(f"Inconsistent trend snapshots for {week}")
        ranked = []
        if run.current_items and snapshots:
            analyzer = TrendEvolutionAnalyzer(self._access, clock=lambda: now)
            histories = {
                row.trend_id: row for row in analyzer.analyze_all_trends(self._weeks, end_week=week)
            }
            ordered = sorted(
                snapshots, key=lambda row: (-row.trend_score, row.type, row.name, row.trend_id)
            )
            for position, snapshot in enumerate(ordered, 1):
                if snapshot.trend_id not in histories:
                    raise ValueError(f"Missing evolution for {snapshot.trend_id}")
                ranked.append(
                    RankedTrend(
                        rank=position,
                        trend=Trend.model_validate(
                            snapshot.model_dump(include=set(Trend.model_fields))
                        ),
                        evolution=histories[snapshot.trend_id],
                    )
                )
        self._check_unchanged(run, snapshots)
        report = TrendRanking(
            week=week,
            run=run,
            status=(
                "empty_current"
                if not run.current_items
                else "baseline_empty"
                if not run.baseline_items
                else "ready"
            ),
            evolution_weeks=self._weeks,
            top_growing=self._positions(
                [
                    row
                    for row in ranked
                    if row.trend.delta_percent is not None and row.trend.delta_percent > 0
                ][:10]
            ),
            top_declining=self._positions(
                [
                    row
                    for row in ranked
                    if row.trend.delta_percent is not None and row.trend.delta_percent < 0
                ][:10]
            ),
            top_by_type={
                kind: self._positions([row for row in ranked if row.trend.type == kind])
                for kind in KINDS
            },
        )
        logger.info(
            "Trend ranking: week=%s, status=%s, candidates=%d", week, report.status, len(ranked)
        )
        return report

    def _check_unchanged(self, run: TrendRun, snapshots: list[TrendSnapshot]) -> None:
        # Compare payloads too: storage permits reruns with equal computed_at.
        latest = self._access.list_trend_snapshots(run.week)
        if (
            self._access.get_trend_run(run.week) != run
            or len(latest) != len(snapshots)
            or {row.trend_id: row for row in latest} != {row.trend_id: row for row in snapshots}
        ):
            raise RuntimeError(f"Trend run changed while ranking {run.week}; retry ranking")

    @staticmethod
    def _positions(rows: list[RankedTrend]) -> list[RankedTrend]:
        return [row.model_copy(update={"rank": position}) for position, row in enumerate(rows, 1)]

    @staticmethod
    def generate_summary_markdown(ranking: TrendRanking) -> str:
        """Render saved ranking values; show at most ten rows per type, with escaped names."""
        run = ranking.run
        lines = [
            f"# Weekly trend ranking — {ranking.week}",
            "",
            f"Baseline: {run.baseline_week}. Status: {ranking.status}.",
            f"Observed items: current={run.current_items}, baseline={run.baseline_items}.",
            f"Identification computed at: {run.computed_at.isoformat()}.",
            f"Evolution window: {ranking.evolution_weeks} completed UTC weeks "
            f"ending {ranking.week}.",
            "",
            "All lists use trend score descending; declining is not ordered by decline magnitude.",
            "Counts describe analyzed observations, not complete ingestion or source coverage.",
            "Ranking uses all saved candidates, "
            "including those below the identification threshold.",
        ]
        if ranking.status == "empty_current":
            lines.extend(["", "No current observations; change rankings are suppressed."])
        elif ranking.status == "baseline_empty":
            lines.extend(["", "Baseline has no observations; growth percentages are undefined."])
        sections = [
            ("Growing vs baseline", ranking.top_growing),
            ("Declining vs baseline", ranking.top_declining),
            *((f"By type: {kind}", ranking.top_by_type[kind]) for kind in KINDS),
        ]
        for title, rows in sections:
            lines.extend(["", f"## {title}", ""])
            if not rows:
                lines.append("No eligible trends.")
                continue
            lines.extend(
                [
                    f"Showing {min(10, len(rows))} of {len(rows)} ranked entries.",
                    "",
                    "| Rank | Type | Name | Current | Baseline | Change | Score | Evolution |",
                    "| --- | --- | --- | --- | --- | --- | --- | --- |",
                ]
            )
            for row in rows[:10]:
                trend, evolution = row.trend, row.evolution
                delta = (
                    f"{trend.delta_percent:+.2f}%"
                    if trend.delta_percent is not None
                    else "new in comparison"
                    if trend.comparison == "new"
                    else "undefined (empty baseline)"
                )
                state = evolution.pattern or evolution.status
                history = f"{state}; observed {evolution.observed_weeks}/{ranking.evolution_weeks}"
                if evolution.volatility is not None:
                    history += f"; CV={evolution.volatility:.4f}"
                lines.append(
                    f"| {row.rank} | {trend.type} | {_escape_cell(trend.name)} | "
                    f"{trend.current_count} | {trend.baseline_count} | {delta} | "
                    f"{trend.trend_score:.4f} | {history} |"
                )
        return "\n".join(lines) + "\n"


def _escape_cell(value: str) -> str:
    """Keep untrusted labels as single-line text in Markdown table cells."""
    text = html.escape(" ".join(value.split()), quote=False)
    return re.sub(r"([\\`*_{}\[\]()#+.!|~-])", r"\\\1", text)
