"""Evolution classification, missing observations and persisted eight-week history."""

from datetime import datetime, timedelta, timezone
from math import sqrt
from unittest.mock import MagicMock
from uuid import NAMESPACE_URL, uuid5

import pytest

from app.services.repository.access_service import RepositoryAccessService
from app.services.trend.evolution import TrendEvolutionAnalyzer
from app.services.trend.models import (
    TrendEvolution,
    TrendRun,
    TrendSnapshot,
    WeeklyCount,
    trend_identity,
    week_label,
    week_start,
)
from app.storage.knowledge.sqlite_store import SQLiteKnowledgeStore

NOW = datetime(2026, 10, 19, tzinfo=timezone.utc)
TREND_ID = trend_identity("topic", "rag")


def snapshot(week, count, kind="topic", name="rag"):
    identity = trend_identity(kind, name)
    delta = (count - 1) * 100
    normalized = min(1, max(-1, delta / 100))
    return TrendSnapshot(
        trend_id=identity,
        type=kind,
        name=name,
        current_count=count,
        baseline_count=1,
        delta_percent=delta,
        comparison="comparable",
        rank_change=0,
        normalized_delta=normalized,
        normalized_count=1 if count else 0,
        rank_bonus=0,
        trend_score=0.6 * normalized + (0.3 if count else 0),
        sample_knowledge_ids=[],
        snapshot_id=str(uuid5(NAMESPACE_URL, f"{identity}:{week}")),
        week=week,
        baseline_week=week_label(week_start(week) - timedelta(days=7)),
        computed_at=NOW,
    )


def history(counts, *, end="2026-W42", missing=(), empty=(), absent=()):
    runs, rows = {}, {}
    for index, count in enumerate(counts):
        week = week_label(week_start(end) - timedelta(weeks=len(counts) - index - 1))
        if index in missing:
            runs[week], rows[week] = None, []
            continue
        records = [] if index in absent else [snapshot(week, count)]
        runs[week] = TrendRun(
            week=week,
            baseline_week=week_label(week_start(week) - timedelta(days=7)),
            computed_at=NOW,
            current_items=0 if index in empty else max(count, 1),
            baseline_items=1,
            snapshot_count=len(records),
            min_count=3,
        )
        rows[week] = records
    access = MagicMock(spec=RepositoryAccessService)
    access.get_trend_run.side_effect = lambda week: runs.get(week)
    access.list_trend_snapshots.side_effect = lambda week: rows.get(week, [])
    return access, runs, rows


def analyze(counts, **kwargs):
    access, _, _ = history(counts, **kwargs)
    return TrendEvolutionAnalyzer(access, clock=lambda: NOW).analyze_evolution(
        TREND_ID, len(counts)
    )


@pytest.mark.parametrize(
    "counts, pattern",
    [
        ([1, 2, 4, 8, 16, 32, 64, 128], "growing"),
        ([128, 64, 32, 16, 8, 4, 2, 1], "declining"),
        ([100, 101, 99, 100, 100, 99, 101, 100], "stable"),
        ([1, 9, 1, 9, 1, 9, 1, 9], "volatile"),
    ],
)
def test_eight_week_patterns_and_population_volatility(counts, pattern):
    result = analyze(counts)
    assert result.pattern == pattern and result.status == "classified"
    assert [point.count for point in result.weekly_counts] == counts
    assert [point.week for point in result.weekly_counts] == [
        f"2026-W{number}" for number in range(35, 43)
    ]
    mean = sum(counts) / len(counts)
    expected = sqrt(sum((value - mean) ** 2 for value in counts) / len(counts)) / mean
    assert result.volatility == pytest.approx(expected)


@pytest.mark.parametrize("counts", [[80, 120] * 4, [70, 130] * 4, [50, 150] * 4])
def test_threshold_boundaries_and_middle_band_remain_unclassified(counts):
    result = analyze(counts)
    assert result.status == "unclassified" and result.pattern is None
    assert result.volatility is not None


def test_growth_is_strictly_above_ten_percent_and_direction_has_precedence():
    assert analyze([100, 110, 121]).pattern == "stable"
    assert analyze([100, 111, 124]).pattern == "growing"
    assert analyze([100, 99, 98]).pattern == "declining"
    assert analyze([0, 10, 20]).pattern == "volatile"


def test_all_zero_observed_series_has_no_activity():
    result = analyze([0] * 8)
    assert result.status == "no_activity"
    assert result.pattern is None and result.volatility == 0
    assert result.observed_weeks == 8


@pytest.mark.parametrize("missing", [(0,), (3,), (7,)])
def test_missing_week_is_not_zero_or_backfilled_from_baseline(missing):
    result = analyze([10] * 8, missing=missing)
    assert result.weekly_counts[missing[0]].count is None
    assert result.weekly_counts[missing[0]].status == "missing_run"
    assert result.observed_weeks == 7
    assert result.status == "insufficient_history"
    assert result.pattern is result.volatility is None


def test_empty_run_and_absent_signal_have_different_observation_semantics():
    counts = [10, 10, 10, 0, 10, 10, 10, 10]
    empty = analyze(counts, empty=(3,))
    assert empty.weekly_counts[3].count == 0
    assert empty.weekly_counts[3].status == "empty_run"
    assert empty.status == "insufficient_history"
    absent = analyze(counts, absent=(3,))
    assert absent.weekly_counts[3].count == 0
    assert absent.weekly_counts[3].status == "observed"
    assert absent.observed_weeks == 8
    assert absent.volatility is not None


@pytest.mark.parametrize("counts", [[10], [10, 20]])
def test_too_short_history_retains_counts_without_classifying(counts):
    result = analyze(counts)
    assert result.status == "insufficient_history"
    assert result.pattern is result.volatility is None


def test_batch_reads_each_week_once_and_includes_disappearing_candidates():
    access, runs, rows = history([10, 10, 10, 0, 0, 0, 0, 0])
    for week, records in rows.items():
        records.insert(0, snapshot(week, 1, kind="entity", name="rag"))
        runs[week] = runs[week].model_copy(update={"snapshot_count": 2})
    analyzer = TrendEvolutionAnalyzer(access, clock=lambda: NOW)
    results = analyzer.analyze_all_trends()
    assert [(row.type, row.name) for row in results] == [("entity", "rag"), ("topic", "rag")]
    assert results[0].trend_id != results[1].trend_id
    assert results[1].weekly_counts[-1].count == 0
    assert access.list_trend_snapshots.call_count == 8
    assert access.get_trend_run.call_count == 16
    access.save_trend_snapshots.assert_not_called()


def test_empty_window_and_unknown_id():
    access, _, _ = history([0] * 8, missing=range(8))
    analyzer = TrendEvolutionAnalyzer(access, clock=lambda: NOW)
    assert analyzer.analyze_all_trends() == []
    with pytest.raises(LookupError, match="No snapshots"):
        analyzer.analyze_evolution(TREND_ID)
    access.list_trend_snapshots.assert_not_called()


def test_explicit_end_week_iso_year_and_utc_default():
    access, _, _ = history([2, 3, 4], end="2020-W53")
    result = TrendEvolutionAnalyzer(access, clock=lambda: NOW).analyze_evolution(
        TREND_ID, 3, end_week="2020-W53"
    )
    assert [point.week for point in result.weekly_counts] == ["2020-W51", "2020-W52", "2020-W53"]
    local = datetime(2026, 10, 19, 0, 30, tzinfo=timezone(timedelta(hours=7)))
    access, _, _ = history([2, 3, 4], end="2026-W41")
    result = TrendEvolutionAnalyzer(access, clock=lambda: local).analyze_evolution(TREND_ID, 3)
    assert result.weekly_counts[-1].week == "2026-W41"


@pytest.mark.parametrize("weeks", [0, -1, True, 1.5, 10**10])
def test_invalid_window_fails_before_repository_reads(weeks):
    access = MagicMock(spec=RepositoryAccessService)
    analyzer = TrendEvolutionAnalyzer(access, clock=lambda: NOW)
    with pytest.raises(ValueError):
        analyzer.analyze_all_trends(weeks)
    access.get_trend_run.assert_not_called()


@pytest.mark.parametrize("end", ["2026-W43", "2026-W44", "2026-W2", "2025-W53"])
def test_invalid_or_incomplete_end_week(end):
    access = MagicMock(spec=RepositoryAccessService)
    with pytest.raises(ValueError):
        TrendEvolutionAnalyzer(access, clock=lambda: NOW).analyze_all_trends(end_week=end)
    access.get_trend_run.assert_not_called()


def test_naive_clock_and_storage_errors_propagate():
    access = MagicMock(spec=RepositoryAccessService)
    with pytest.raises(ValueError, match="timezone-aware"):
        TrendEvolutionAnalyzer(access, clock=lambda: NOW.replace(tzinfo=None)).analyze_all_trends()
    access.get_trend_run.side_effect = RuntimeError("database unavailable")
    with pytest.raises(RuntimeError, match="database unavailable"):
        TrendEvolutionAnalyzer(access, clock=lambda: NOW).analyze_all_trends()


def test_changed_run_and_inconsistent_snapshot_batch_fail():
    access, runs, rows = history([10])
    run = runs["2026-W42"]
    access.get_trend_run.side_effect = [
        run,
        run.model_copy(update={"computed_at": NOW + timedelta(seconds=1)}),
    ]
    with pytest.raises(RuntimeError, match="changed while reading"):
        TrendEvolutionAnalyzer(access, clock=lambda: NOW).analyze_all_trends(1)
    access.get_trend_run.side_effect = lambda week: runs[week]
    rows["2026-W42"].clear()
    with pytest.raises(ValueError, match="Inconsistent"):
        TrendEvolutionAnalyzer(access, clock=lambda: NOW).analyze_all_trends(1)


def test_models_reject_contradictory_observations_and_unordered_weeks():
    with pytest.raises(ValueError):
        WeeklyCount(week="2026-W42", count=0, status="missing_run")
    with pytest.raises(ValueError):
        WeeklyCount(week="2026-W42", count=1, status="empty_run")
    result = analyze([10] * 3)
    data = result.model_dump()
    data["weekly_counts"].reverse()
    with pytest.raises(ValueError, match="chronological"):
        TrendEvolution.model_validate(data)


def test_real_sqlite_history_survives_reopen_and_evolution_does_not_write(tmp_path):
    path = tmp_path / "trends.db"
    _, runs, rows = history([1, 2, 4, 8, 16, 32, 64, 128])
    store = SQLiteKnowledgeStore(path)
    access = RepositoryAccessService(store)
    for week in runs:
        access.save_trend_snapshots(rows[week], run=runs[week])
    store.close()
    store = SQLiteKnowledgeStore(path)
    try:
        access = RepositoryAccessService(store)
        before = store.conn_manager.get_connection().total_changes
        result = TrendEvolutionAnalyzer(access, clock=lambda: NOW).analyze_evolution(TREND_ID)
        assert result.pattern == "growing"
        assert len(result.weekly_counts) == 8
        assert store.conn_manager.get_connection().total_changes == before
        assert access.get_trend_run("2026-W42") == runs["2026-W42"]
    finally:
        store.close()
