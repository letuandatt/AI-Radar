"""Weekly ranking contracts, deterministic output and real SQLite readback."""

from datetime import timedelta
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
)
from app.services.trend.ranker import TrendRanker
from app.storage.knowledge.sqlite_store import SQLiteKnowledgeStore
from tests.services.trend.test_evolution import NOW

WEEK = "2026-W42"


def snapshot(index, count, baseline, *, kind=None, name=None, baseline_empty=False):
    kind = kind or ("topic", "source", "entity")[index % 3]
    name = name or f"signal-{index:02d}"
    identity = trend_identity(kind, name)
    delta = (count - baseline) / baseline * 100 if baseline else None
    normalized = min(1, max(-1, delta / 100)) if delta is not None else 0 if baseline_empty else 1
    return TrendSnapshot(
        trend_id=identity,
        type=kind,
        name=name,
        current_count=count,
        baseline_count=baseline,
        delta_percent=delta,
        comparison="comparable" if baseline else "baseline_empty" if baseline_empty else "new",
        rank_change=0,
        normalized_delta=normalized,
        normalized_count=count / 100,
        rank_bonus=0,
        trend_score=0.6 * normalized + 0.3 * count / 100,
        sample_knowledge_ids=[],
        snapshot_id=str(uuid5(NAMESPACE_URL, f"{identity}:{WEEK}")),
        week=WEEK,
        baseline_week="2026-W41",
        computed_at=NOW,
    )


def fifty_trends():
    return (
        [snapshot(i, 11 + i, 10) for i in range(20)]
        + [snapshot(i, i - 20, 30) for i in range(20, 40)]
        + [snapshot(i, 10, 10) for i in range(40, 45)]
        + [snapshot(i, i - 44, 0) for i in range(45, 50)]
    )


def setup(rows=None, *, current_items=100, baseline_items=100):
    rows = fifty_trends() if rows is None else rows
    run = TrendRun(
        week=WEEK,
        baseline_week="2026-W41",
        computed_at=NOW,
        current_items=current_items,
        baseline_items=baseline_items,
        snapshot_count=len(rows),
        min_count=3,
    )
    access = MagicMock(spec=RepositoryAccessService)
    access.get_trend_run.side_effect = lambda week: run if week == WEEK else None
    access.list_trend_snapshots.side_effect = lambda week: rows if week == WEEK else []
    return TrendRanker(access, clock=lambda: NOW), access, run, rows


def test_fifty_trends_top_ten_order_groups_and_local_positions():
    ranker, access, run, rows = setup()
    result = ranker.rank_trends(WEEK)
    assert len(rows) == 50
    assert result.run == run and result.status == "ready"
    assert [row.trend.current_count for row in result.top_growing] == list(range(30, 20, -1))
    assert [row.trend.current_count for row in result.top_declining] == list(range(19, 9, -1))
    assert sum(map(len, result.top_by_type.values())) == 50
    for kind, group in result.top_by_type.items():
        assert all(row.trend.type == kind for row in group)
        assert [row.rank for row in group] == list(range(1, len(group) + 1))
        assert [row.trend.trend_score for row in group] == sorted(
            [row.trend.trend_score for row in group], reverse=True
        )
    for group in (result.top_growing, result.top_declining):
        assert [row.rank for row in group] == list(range(1, 11))
    assert all(row.trend.delta_percent > 0 for row in result.top_growing)
    assert all(row.trend.delta_percent < 0 for row in result.top_declining)
    access.save_trend_snapshots.assert_not_called()


def test_ties_input_order_new_and_below_threshold_candidates():
    rows = fifty_trends()
    first = setup(rows)[0].rank_trends(WEEK)
    second = setup(list(reversed(rows)))[0].rank_trends(WEEK)
    assert first == second
    flattened = [item for group in first.top_by_type.values() for item in group]
    assert any(
        item.trend.comparison == "new" and item.trend.current_count == 1 for item in flattened
    )
    tied = [snapshot(i, 10, 10, kind="topic") for i in (3, 1, 2)]
    assert [item.trend.name for item in setup(tied)[0].rank_trends(WEEK).top_by_type["topic"]] == [
        "signal-01",
        "signal-02",
        "signal-03",
    ]


def test_disappeared_signal_is_ranked_when_current_cohort_is_observed():
    result = setup([snapshot(0, 0, 10)])[0].rank_trends(WEEK)
    assert result.top_declining[0].trend.current_count == 0
    assert result.top_declining[0].trend.delta_percent == -100
    assert result.top_declining[0].evolution.status == "insufficient_history"


def test_weekly_growth_is_independent_of_evolution_pattern(monkeypatch):
    row = snapshot(0, 20, 10)
    evolution = TrendEvolution(
        trend_id=row.trend_id,
        type=row.type,
        name=row.name,
        weekly_counts=[
            WeeklyCount(week=f"2026-W{35 + i}", count=count, status="observed")
            for i, count in enumerate([1, 20] * 4)
        ],
        observed_weeks=8,
        pattern="volatile",
        volatility=19 / 21,
        status="classified",
    )
    monkeypatch.setattr(TrendEvolutionAnalyzer, "analyze_all_trends", lambda *a, **kw: [evolution])
    result = setup([row])[0].rank_trends(WEEK)
    assert result.top_growing[0].evolution.pattern == "volatile"


def test_new_signal_is_displayed_without_a_percentage():
    result = setup([snapshot(0, 1, 0)])[0].rank_trends(WEEK)
    assert result.top_growing == result.top_declining == []
    markdown = TrendRanker.generate_summary_markdown(result)
    assert "new in comparison" in markdown
    assert "+100.00%" not in markdown


@pytest.mark.parametrize("rows", [[], [snapshot(0, 0, 10)]])
def test_empty_current_suppresses_false_declines(rows, monkeypatch):
    forbidden = MagicMock(side_effect=AssertionError("Empty cohort needs no evolution"))
    monkeypatch.setattr(TrendEvolutionAnalyzer, "analyze_all_trends", forbidden)
    result = setup(rows, current_items=0)[0].rank_trends(WEEK)
    assert result.status == "empty_current"
    assert result.top_growing == result.top_declining == []
    assert all(group == [] for group in result.top_by_type.values())
    assert "change rankings are suppressed" in TrendRanker.generate_summary_markdown(result)
    forbidden.assert_not_called()


def test_empty_baseline_does_not_invent_growth_percentages():
    rows = [snapshot(i, i + 1, 0, baseline_empty=True) for i in range(3)]
    result = setup(rows, baseline_items=0)[0].rank_trends(WEEK)
    assert result.status == "baseline_empty"
    assert result.top_growing == result.top_declining == []
    assert sum(map(len, result.top_by_type.values())) == 3
    markdown = TrendRanker.generate_summary_markdown(result)
    assert "undefined (empty baseline)" in markdown and "+100.00%" not in markdown


def test_evolution_is_batched_and_anchored_to_historical_week(monkeypatch):
    original = TrendEvolutionAnalyzer.analyze_all_trends
    calls = []

    def tracked(self, weeks=8, *, end_week=None):
        calls.append((weeks, end_week))
        return original(self, weeks, end_week=end_week)

    monkeypatch.setattr(TrendEvolutionAnalyzer, "analyze_all_trends", tracked)
    _, access, _, _ = setup()
    result = TrendRanker(access, clock=lambda: NOW + timedelta(weeks=4)).rank_trends(WEEK)
    assert calls == [(8, WEEK)]
    for group in result.top_by_type.values():
        for row in group:
            assert row.evolution.weekly_counts[-1].week == WEEK
            assert row.evolution.weekly_counts[-1].count == row.trend.current_count
            assert row.evolution.pattern is None


def test_markdown_escapes_labels_and_limits_only_the_presentation():
    name = "<b>A|B</b>\n[x](url) `code` \\ test"
    rows = [snapshot(i, 20, 10, kind="topic") for i in range(50)]
    rows[0] = snapshot(0, 20, 10, kind="topic", name=name)
    result = setup(rows)[0].rank_trends(WEEK)
    markdown = TrendRanker.generate_summary_markdown(result)
    assert "&lt;b&gt;A\\|B&lt;/b&gt;" in markdown
    assert "\\[x\\]\\(url\\)" in markdown and "\\`code\\`" in markdown
    assert "<b>" not in markdown and "</b>\n" not in markdown
    assert "Showing 10 of 50 ranked entries." in markdown
    assert "signal-49" not in markdown
    assert len(result.model_dump()["top_by_type"]["topic"]) == 50
    assert "insufficient_history" in markdown
    assert "not ordered by decline magnitude" in markdown
    assert markdown == TrendRanker.generate_summary_markdown(result)


def test_missing_run_invalid_week_and_storage_failure():
    ranker, access, _, _ = setup()
    with pytest.raises(LookupError, match="identification first"):
        ranker.rank_trends("2026-W40")
    for week in ("2026-W43", "2026-W2", "2025-W53"):
        with pytest.raises(ValueError):
            ranker.rank_trends(week)
    access.get_trend_run.side_effect = RuntimeError("database unavailable")
    with pytest.raises(RuntimeError, match="database unavailable"):
        ranker.rank_trends(WEEK)


@pytest.mark.parametrize("weeks", [0, -1, True, 1.5])
def test_invalid_history_window(weeks):
    with pytest.raises(ValueError):
        TrendRanker(MagicMock(), evolution_weeks=weeks)


def test_naive_clock_and_overflow_fail_before_reads():
    access = MagicMock(spec=RepositoryAccessService)
    with pytest.raises(ValueError, match="timezone-aware"):
        TrendRanker(access, clock=lambda: NOW.replace(tzinfo=None)).rank_trends(WEEK)
    with pytest.raises(ValueError, match="datetime range"):
        TrendRanker(access, evolution_weeks=10**10, clock=lambda: NOW).rank_trends(WEEK)
    access.get_trend_run.assert_not_called()


def test_inconsistent_batch_and_same_timestamp_rerun_are_rejected():
    rows = fifty_trends()
    ranker, access, run, _ = setup(rows)
    access.get_trend_run.side_effect = lambda week: run.model_copy(update={"snapshot_count": 49})
    with pytest.raises(ValueError, match="Inconsistent"):
        ranker.rank_trends(WEEK)
    ranker, access, _, _ = setup(rows)
    calls = 0

    def read(week):
        nonlocal calls
        calls += 1
        if calls == 3:
            return [rows[0].model_copy(update={"sample_knowledge_ids": ["changed"]}), *rows[1:]]
        return rows

    access.list_trend_snapshots.side_effect = read
    with pytest.raises(RuntimeError, match="changed while ranking"):
        ranker.rank_trends(WEEK)


def test_sqlite_round_trip_ranking_does_not_write(tmp_path):
    _, _, run, rows = setup()
    store = SQLiteKnowledgeStore(tmp_path / "trends.db")
    try:
        access = RepositoryAccessService(store)
        access.save_trend_snapshots(rows, run=run)
        before = store.conn_manager.get_connection().total_changes
        result = TrendRanker(access, clock=lambda: NOW).rank_trends(WEEK)
        assert len(result.top_growing) == len(result.top_declining) == 10
        assert store.conn_manager.get_connection().total_changes == before
        assert access.get_trend_run(WEEK) == run
    finally:
        store.close()
