"""Real temporary SQLite tests: boundaries, reruns, empty runs and rollback."""

import sqlite3
from datetime import timedelta, timezone

import pytest

from app.services.repository.access_service import RepositoryAccessService
from app.services.trend.identifier import TrendIdentifier
from app.services.trend.models import week_start
from app.storage.knowledge.sqlite_store import SQLiteKnowledgeStore
from tests.fakes.analysis import make_knowledge
from tests.services.trend.test_identifier import NOW, hundred_items, item


@pytest.fixture
def repository(tmp_path):
    path = tmp_path / "knowledge.db"
    store = SQLiteKnowledgeStore(path)
    yield path, store, RepositoryAccessService(store)
    store.close()


def seed(store, access, rows):
    store.save_objects([make_knowledge(row) for row in rows])
    for row in rows:
        access.save_content_analysis(row)
        with store.conn_manager.get_connection() as conn:
            conn.execute(
                "UPDATE content_analyses SET created_at = ? WHERE knowledge_id = ?",
                (row.first_observed_at.isoformat(), row.knowledge_id),
            )


def test_rerun_readback_stable_ids_and_below_threshold_candidates(repository):
    path, store, access = repository
    seed(store, access, hundred_items())
    identifier = TrendIdentifier(access, clock=lambda: NOW)
    first = identifier.get_weekly_trends()
    saved = access.list_trend_snapshots(first.week)
    identifier.get_weekly_trends()
    assert access.list_trend_snapshots(first.week) == saved
    assert access.get_trend_run(first.week).snapshot_count == len(saved)
    store.close()
    reopened = SQLiteKnowledgeStore(path)
    try:
        loaded = RepositoryAccessService(reopened).list_trend_snapshots(first.week)
        assert loaded == saved
        assert any(row.name == "legacy" and row.current_count == 0 for row in loaded)
        assert len({row.snapshot_id for row in loaded}) == len(saved)
    finally:
        reopened.close()


def test_half_open_boundaries_offsets_deletion_and_first_observed(repository):
    _, store, access = repository
    start = week_start("2026-W42")
    end = start + timedelta(days=7)
    instants = [
        start - timedelta(microseconds=1),
        start,
        end - timedelta(microseconds=1),
        end,
        (start + timedelta(hours=2)).astimezone(timezone(timedelta(hours=7))),
    ]
    rows = [
        item(i, "2026-W42").model_copy(update={"first_observed_at": at})
        for i, at in enumerate(instants)
    ]
    seed(store, access, rows)
    store.delete_by_id("ko-4")
    # Saving a newer analysis must preserve the original created_at/week.
    access.save_content_analysis(
        rows[1].model_copy(update={"analyzed_at": NOW + timedelta(days=5)})
    )
    found = access.list_trend_items(start, end)
    assert {row.knowledge_id for row in found} == {"ko-1", "ko-2"}
    with store.conn_manager.get_connection() as conn:
        conn.execute("UPDATE knowledge_objects SET deleted_at = NULL WHERE id = ?", ("ko-4",))
    assert {row.knowledge_id for row in access.list_trend_items(start, end)} == {
        "ko-1",
        "ko-2",
        "ko-4",
    }
    with pytest.raises(ValueError):
        access.list_trend_items(start.replace(tzinfo=None), end)


def test_empty_run_replaces_old_candidates_but_other_weeks_survive(repository):
    _, store, access = repository
    seed(store, access, hundred_items())
    identifier = TrendIdentifier(access, clock=lambda: NOW)
    identifier.get_weekly_trends("2026-W41", "2026-W40")
    identifier.get_weekly_trends()
    previous = access.list_trend_snapshots("2026-W41")
    store.delete_by_source("rss", "a")
    store.delete_by_source("rss", "b")
    result = identifier.get_weekly_trends()
    assert result.trends == []
    assert access.list_trend_snapshots("2026-W42") == []
    assert access.get_trend_run("2026-W42").snapshot_count == 0
    assert access.get_trend_run("2026-W40") is None
    assert access.list_trend_snapshots("2026-W41") == previous


def test_atomic_rollback_and_stale_run_rejection(repository):
    _, store, access = repository
    seed(store, access, hundred_items())
    TrendIdentifier(access, clock=lambda: NOW).get_weekly_trends()
    saved = access.list_trend_snapshots("2026-W42")
    run = access.get_trend_run("2026-W42")
    records = [row.model_dump(mode="json") for row in saved]
    newer = run.model_copy(update={"computed_at": NOW + timedelta(seconds=1)})
    # Fail after the first INSERT, so DELETE + run update must both roll back.
    with pytest.raises(sqlite3.IntegrityError):
        store.save_trend_snapshots([records[0], records[0]], newer.model_dump(mode="json"))
    assert access.get_trend_run(run.week) == run
    assert access.list_trend_snapshots(run.week) == saved
    with pytest.raises(ValueError, match="newer trend run"):
        store.save_trend_snapshots(
            records,
            run.model_copy(update={"computed_at": NOW - timedelta(seconds=1)}).model_dump(
                mode="json"
            ),
        )
    assert access.list_trend_snapshots(run.week) == saved


def test_access_rejects_inconsistent_batch_before_mutation(repository):
    _, store, access = repository
    seed(store, access, hundred_items())
    TrendIdentifier(access, clock=lambda: NOW).get_weekly_trends()
    run = access.get_trend_run("2026-W42")
    saved = access.list_trend_snapshots(run.week)
    with pytest.raises(ValueError, match="snapshot_count"):
        access.save_trend_snapshots([], run=run)
    with pytest.raises(ValueError, match="Duplicate"):
        access.save_trend_snapshots(
            [saved[0], saved[0]], run=run.model_copy(update={"snapshot_count": 2})
        )
    assert access.list_trend_snapshots(run.week) == saved
