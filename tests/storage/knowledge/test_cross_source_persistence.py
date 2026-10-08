"""Real SQLite window queries and atomic cross-source snapshots."""

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from time import perf_counter
from unittest.mock import MagicMock

import pytest

from app.services.analysis.cross_source_analyzer import CrossSourceAnalyzer
from app.services.repository.access_service import RepositoryAccessService
from app.storage.knowledge.sqlite_store import SQLiteKnowledgeStore
from tests.fakes.analysis import NOW, make_analysis, make_knowledge, twenty_analyses


@pytest.fixture
def repository(tmp_path, monkeypatch):
    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW

    monkeypatch.setattr("app.services.repository.access_service.datetime", FrozenDateTime)
    path = tmp_path / "knowledge.db"
    store = SQLiteKnowledgeStore(path)
    access = RepositoryAccessService(store)
    yield store, access, path
    store.close()


def seed(store, access, items):
    store.save_objects([make_knowledge(item) for item in items])
    for item in items:
        access.save_content_analysis(item)


def read_groups(path, days=7):
    with sqlite3.connect(path) as conn:
        return conn.execute(
            "SELECT group_id, topic, knowledge_ids_json, coverage_score "
            "FROM cross_source_groups WHERE time_window_days = ? ORDER BY topic",
            (days,),
        ).fetchall()


def test_window_uses_analysis_time_offsets_boundaries_and_live_objects(repository):
    store, access, path = repository
    cutoff = NOW - timedelta(days=7)
    items = [
        make_analysis(0, at=cutoff),
        make_analysis(1, at=cutoff.astimezone(timezone(timedelta(hours=7)))),
        make_analysis(2, at=cutoff - timedelta(seconds=1)),
        make_analysis(3, at=NOW),
        make_analysis(4, at=NOW + timedelta(seconds=1)),
        make_analysis(5),
    ]
    seed(store, access, items)
    store.save_objects([make_knowledge(make_analysis(6))])  # No analysis yet.
    with sqlite3.connect(path) as conn:
        conn.execute(
            "UPDATE knowledge_objects SET deleted_at = ? WHERE id = 'ko-5'", (NOW.isoformat(),)
        )
    result = access.list_items_in_window()
    assert [item.knowledge_id for item in result] == ["ko-0", "ko-1", "ko-3"]
    assert result[0].source_name == "a"
    assert result[0].themes == ["RAG"]
    assert result[0].analyzed_at == cutoff
    # Knowledge publication dates are 100 days old and do not control this window.


def test_snapshot_round_trip_rerun_replacement_and_window_isolation(repository):
    store, access, path = repository
    items = twenty_analyses()
    seed(store, access, items)
    analyzer = CrossSourceAnalyzer(access, MagicMock(), max_groups=1)
    first = analyzer.find_groups()
    rows = read_groups(path)
    assert len(rows) == 2  # Persist everything, not just top 1.
    assert set(json.loads(rows[0][2])) == {f"ko-{i}" for i in range(14)}
    assert rows[0][3] == pytest.approx(2 / 3)
    assert analyzer.find_groups() == first
    assert read_groups(path) == rows
    analyzer.find_groups(30)
    assert len(read_groups(path, 30)) == 2

    # Change the topic on the current analyses: obsolete groups must disappear.
    for item in items:
        access.save_content_analysis(
            make_analysis(int(item.knowledge_id[3:]), item.source_name, ["New"], at=NOW)
        )
    assert analyzer.find_groups()[0].topic == "theme:new"
    assert len(read_groups(path)) == 1
    assert len(read_groups(path, 30)) == 2

    access.save_cross_source_groups([], time_window_days=7)
    assert read_groups(path) == []
    assert len(read_groups(path, 30)) == 2
    reopened = SQLiteKnowledgeStore(path)
    try:
        assert len(read_groups(path, 30)) == 2
    finally:
        reopened.close()


def test_failed_snapshot_insert_rolls_back_previous_snapshot(repository):
    store, access, path = repository
    seed(store, access, twenty_analyses())
    groups = CrossSourceAnalyzer(access, MagicMock()).find_groups()
    original = read_groups(path)
    with pytest.raises(sqlite3.IntegrityError):
        access.save_cross_source_groups([groups[0], groups[0]])
    assert read_groups(path) == original


@pytest.mark.performance
def test_sqlite_to_groups_for_one_thousand_objects_under_five_seconds(repository):
    store, access, path = repository
    items = [make_analysis(i, str(i % 3), [f"topic-{i % 20}"]) for i in range(1000)]
    seed(store, access, items)
    analyzer = CrossSourceAnalyzer(access, MagicMock())
    start = perf_counter()
    groups = analyzer.find_groups()
    elapsed = perf_counter() - start
    assert len(groups) == 20
    assert sum(len(group.knowledge_ids) for group in groups) == 1000
    assert len(read_groups(path)) == 20
    assert elapsed < 5.0
    print(f"SQLite read + grouping + persistence for 1000 items: {elapsed:.4f}s")
