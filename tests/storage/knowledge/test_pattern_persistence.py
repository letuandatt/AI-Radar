"""Real SQLite first-observation queries, atomic daily history and throughput."""

import sqlite3
from datetime import timedelta, timezone
from time import perf_counter
from unittest.mock import MagicMock

import pytest

from app.prompts.loader import PromptLoader
from app.services.analysis.pattern_discoverer import PatternDiscoverer
from app.services.repository.access_service import RepositoryAccessService
from app.storage.knowledge.sqlite_store import SQLiteKnowledgeStore
from tests.fakes.analysis import NOW, make_knowledge
from tests.fakes.patterns import describe, hundred_items, observed, pattern, thousand_items


@pytest.fixture
def repository(tmp_path):
    path = tmp_path / "patterns.db"
    store = SQLiteKnowledgeStore(path)
    yield store, RepositoryAccessService(store), path
    store.close()


def seed(store, access, path, items):
    store.save_objects([make_knowledge(item) for item in items])
    for item in items:
        access.save_content_analysis(item)
    with sqlite3.connect(path) as conn:
        conn.executemany(
            "UPDATE content_analyses SET created_at = ? WHERE knowledge_id = ?",
            [(item.first_observed_at.isoformat(), item.knowledge_id) for item in items],
        )


def counts(path):
    with sqlite3.connect(path) as conn:
        return tuple(
            conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            for table in ("discovered_patterns", "pattern_snapshots")
        )


def test_query_boundaries_offsets_deletion_and_reanalysis(repository):
    store, access, path = repository
    cutoff = NOW - timedelta(days=30)
    items = [
        observed(0, at=cutoff),
        observed(1, at=cutoff.astimezone(timezone(timedelta(hours=7)))),
        observed(2, at=cutoff + timedelta(seconds=1)),
        observed(3, at=NOW),
        observed(4, at=NOW + timedelta(seconds=1)),
        observed(5),
    ]
    seed(store, access, path, items)
    store.delete_by_id("ko-5")
    access.save_content_analysis(observed(2, topic="Revised"))
    rows = access.list_pattern_items(cutoff, NOW)
    assert [row.knowledge_id for row in rows] == ["ko-2", "ko-3"]
    assert rows[0].first_observed_at == cutoff + timedelta(seconds=1)
    assert rows[0].themes == ["Revised"]
    assert rows[0].analyzed_at == NOW
    for start, end in [(NOW, cutoff), (NOW, NOW), (cutoff.replace(tzinfo=None), NOW)]:
        with pytest.raises(ValueError):
            access.list_pattern_items(start, end)


def test_discovery_round_trip_same_day_next_day_and_reopen(repository):
    store, access, path = repository
    seed(store, access, path, hundred_items())
    llm = MagicMock(structured_chat=MagicMock(side_effect=describe))
    clock = MagicMock(return_value=NOW)
    service = PatternDiscoverer(access, llm, PromptLoader(), clock=clock)
    first = service.discover_patterns()
    assert len(first) == 3 and counts(path) == (3, 3)
    assert access.get_pattern_history("missing") == []
    clock.return_value = NOW + timedelta(hours=1)
    second = service.discover_patterns()
    assert counts(path) == (3, 3)
    assert {p.pattern_id for p in first} == {p.pattern_id for p in second}
    assert all(p.first_detected == NOW for p in second)
    clock.return_value = NOW + timedelta(days=1)
    service.discover_patterns()
    assert counts(path) == (3, 6)
    reopened = SQLiteKnowledgeStore(path)
    try:
        history = RepositoryAccessService(reopened).get_pattern_history(first[0].pattern_id)
        assert [p.observed_at for p in history] == [
            NOW + timedelta(hours=1),
            NOW + timedelta(days=1),
        ]
        assert all(p.first_detected == NOW for p in history)
        assert history[0].evidence_ids == first[0].evidence_ids
    finally:
        reopened.close()


def test_daily_key_is_utc_and_stale_runs_cannot_overwrite(repository):
    _, access, path = repository
    p = pattern()
    access.save_discovered_patterns([p], NOW)
    offset_now = (NOW + timedelta(hours=1)).astimezone(timezone(timedelta(hours=14)))
    access.save_discovered_patterns([p], offset_now)
    assert counts(path) == (1, 1)
    before = access.get_pattern_history(p.pattern_id)
    with pytest.raises(ValueError, match="newer"):
        access.save_discovered_patterns([pattern("new", "theme:new"), p], NOW)
    assert counts(path) == (1, 1)  # Earlier inserts in the stale run also roll back.
    assert access.get_pattern_history(p.pattern_id) == before
    with pytest.raises(ValueError, match="unique"):
        access.save_discovered_patterns([p, p], NOW)
    with pytest.raises(ValueError):
        access.save_discovered_patterns([p], NOW.replace(tzinfo=None))


def test_snapshot_failure_rolls_back_current_and_history_tables(repository):
    _, access, path = repository
    p = pattern()
    access.save_discovered_patterns([p], NOW)
    before = access.get_pattern_history(p.pattern_id)
    with sqlite3.connect(path) as conn:
        conn.execute("""CREATE TRIGGER reject_snapshot BEFORE INSERT ON pattern_snapshots
                        WHEN NEW.pattern_id = 'broken'
                        BEGIN SELECT RAISE(ABORT, 'snapshot failure'); END""")
    revised = p.model_copy(update={"description": "Updated description"})
    with pytest.raises(sqlite3.IntegrityError, match="snapshot failure"):
        access.save_discovered_patterns(
            [revised, pattern("broken", "theme:broken")], NOW + timedelta(days=1)
        )
    assert counts(path) == (1, 1)
    assert access.get_pattern_history(p.pattern_id) == before
    with sqlite3.connect(path) as conn:
        payload = conn.execute("SELECT payload_json FROM discovered_patterns").fetchone()[0]
    assert "Updated description" not in payload


@pytest.mark.performance
def test_sqlite_to_patterns_for_thousand_objects_under_ten_seconds(repository):
    store, access, path = repository
    seed(store, access, path, thousand_items())
    llm = MagicMock(structured_chat=MagicMock(side_effect=describe))
    service = PatternDiscoverer(access, llm, PromptLoader(), clock=lambda: NOW)
    start = perf_counter()
    results = service.discover_patterns()
    elapsed = perf_counter() - start
    assert results and elapsed < 10
    assert counts(path) == (len(results), len(results))
    print(f"SQLite read + detection + fake LLM + atomic history, 1000 objects: {elapsed:.4f}s")
