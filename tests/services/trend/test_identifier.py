"""Deterministic identification, filtering and week semantics on typed fixtures."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from app.services.analysis.models import ObservedKnowledgeItem
from app.services.repository.access_service import RepositoryAccessService
from app.services.trend.identifier import TrendIdentifier
from app.services.trend.models import week_label, week_start
from tests.fakes.analysis import make_analysis

NOW = datetime(2026, 10, 19, tzinfo=timezone.utc)


def item(index, week, theme="RAG", source="a"):
    at = week_start(week) + timedelta(hours=1)
    analysis = make_analysis(
        index,
        source,
        [theme, theme.upper(), f" {theme} "],
        {"companies": ["OpenAI", " OpenAI "]} if theme == "RAG" else {"models": ["OpenAI"]},
        at=NOW,
    )
    return ObservedKnowledgeItem(**analysis.model_dump(), first_observed_at=at)


def hundred_items():
    rows = []
    for week, groups in [
        ("2026-W41", [("RAG", 10), ("Vision", 30), ("Legacy", 10)]),
        ("2026-W42", [("RAG", 20), ("Vision", 10), ("Agents", 18), ("Tiny", 2)]),
    ]:
        offset = len(rows)
        for theme, count in groups:
            for _ in range(count):
                position = len(rows) - offset
                source = "a" if position % 5 < (3 if week.endswith("41") else 2) else "b"
                rows.append(item(len(rows), week, theme, source))
    return rows


def setup_service(rows, min_count=3, now=NOW):
    access = MagicMock(spec=RepositoryAccessService)
    access.list_trend_items.return_value = rows
    service = TrendIdentifier(access, min_count=min_count, clock=lambda: now)
    return service, access


def test_hundred_objects_counts_score_evidence_and_unfiltered_storage():
    rows = hundred_items()
    assert len(rows) == 100
    service, access = setup_service(rows)
    report = service.get_weekly_trends()
    assert (report.week, report.baseline_week) == ("2026-W42", "2026-W41")
    assert (report.current_items, report.baseline_items) == (50, 50)
    indexed = {(trend.type, trend.name): trend for trend in report.trends}
    rag = indexed["topic", "rag"]
    assert (rag.current_count, rag.baseline_count, rag.delta_percent) == (20, 10, 100)
    assert rag.rank_change == 1
    assert rag.rank_bonus == 0.25
    assert rag.trend_score == pytest.approx(0.925)
    assert indexed["source", "rss:a"].current_count == 20
    assert indexed["source", "rss:a"].baseline_count == 30
    assert indexed["entity", "companies:openai"].current_count == 20
    assert indexed["entity", "models:openai"].current_count == 30
    assert indexed["topic", "agents"].delta_percent is None
    assert indexed["topic", "agents"].comparison == "new"
    assert indexed["topic", "vision"].trend_score == pytest.approx(-0.3)
    assert len(rag.sample_knowledge_ids) == len(set(rag.sample_knowledge_ids)) == 5
    assert ("topic", "tiny") not in indexed
    assert ("topic", "legacy") not in indexed
    access.save_trend_snapshots.assert_called_once()
    saved = access.save_trend_snapshots.call_args.args[0]
    legacy = next(snapshot for snapshot in saved if snapshot.name == "legacy")
    assert (legacy.current_count, legacy.delta_percent) == (0, -100)
    assert any(snapshot.name == "tiny" for snapshot in saved)
    assert report.snapshot_count == len(saved)
    access.list_trend_items.assert_called_once_with(week_start("2026-W41"), NOW)


def test_repeated_mentions_input_order_and_threshold_do_not_change_scores():
    rows = hundred_items()
    service, access = setup_service(rows + [rows[0]])
    first = service.identify_trends("2026-W42", "2026-W41")
    first_snapshots = access.save_trend_snapshots.call_args.args[0]
    other, another_access = setup_service(list(reversed(rows)), min_count=1)
    second = other.get_weekly_trends().trends
    assert all(trend in second for trend in first)
    assert first_snapshots == another_access.save_trend_snapshots.call_args.args[0]


def test_empty_baseline_is_not_claimed_as_growth_and_empty_run_is_saved():
    service, access = setup_service([item(i, "2026-W42") for i in range(3)])
    report = service.get_weekly_trends()
    assert all(trend.comparison == "baseline_empty" for trend in report.trends)
    assert all(trend.delta_percent is None for trend in report.trends)
    assert all(trend.normalized_delta == trend.rank_bonus == 0 for trend in report.trends)
    assert all(trend.trend_score == pytest.approx(0.3) for trend in report.trends)
    access.list_trend_items.return_value = []
    empty = service.get_weekly_trends()
    assert empty.snapshot_count == 0 and empty.trends == []
    assert access.save_trend_snapshots.call_args.args[0] == []


def test_default_week_crosses_iso_year_and_ignores_reanalysis_date():
    now = datetime(2021, 1, 4, tzinfo=timezone.utc)
    service, _ = setup_service([item(i, "2020-W53") for i in range(3)], now=now)
    report = service.get_weekly_trends()
    assert (report.week, report.baseline_week) == ("2020-W53", "2020-W52")
    assert report.current_items == 3  # analyzed_at is NOW, in 2026.
    assert week_label(week_start("2020-W53")) == "2020-W53"


@pytest.mark.parametrize(
    "week, baseline",
    [
        ("2026-W43", "2026-W42"),
        ("2026-W42", "2026-W42"),
        ("2026-W42", "2026-W43"),
        ("2026-W53", "2026-W41"),
        ("2026-W2", "2026-W01"),
    ],
)
def test_invalid_or_incomplete_weeks_fail_before_storage(week, baseline):
    service, access = setup_service([])
    with pytest.raises(ValueError):
        service.identify_trends(week, baseline)
    access.list_trend_items.assert_not_called()
    access.save_trend_snapshots.assert_not_called()


@pytest.mark.parametrize("minimum", [0, -1, True, 1.5])
def test_invalid_threshold(minimum):
    with pytest.raises(ValueError):
        setup_service([], min_count=minimum)


def test_naive_clock_rejected():
    service, access = setup_service([], now=datetime(2026, 10, 19))
    with pytest.raises(ValueError, match="timezone-aware"):
        service.get_weekly_trends()
    access.list_trend_items.assert_not_called()


def test_storage_failure_propagates():
    service, access = setup_service(hundred_items())
    access.save_trend_snapshots.side_effect = RuntimeError("disk failure")
    with pytest.raises(RuntimeError, match="disk failure"):
        service.get_weekly_trends()
