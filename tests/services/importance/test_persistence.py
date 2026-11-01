"""Real SQLite: upgrades, atomic score replacement, evidence reads and stars transport."""

import sqlite3
from datetime import timedelta

import pytest

from app.fetchers.github_parser import GitHubParser
from app.models.enriched_article import EnrichedArticle
from app.services.importance.config import ImportanceConfig
from app.services.importance.scorer import ImportanceScorer
from app.services.knowledge.object_builder import ObjectBuilder
from app.services.normalization.field_mapper import FieldMapper
from app.services.normalization.standardizer import DataStandardizer
from app.services.repository.access_service import RepositoryAccessService
from app.storage.file_knowledge_store import FileKnowledgeStore
from app.storage.knowledge.schema import KNOWLEDGE_OBJECTS_DDL
from app.storage.knowledge.sqlite_store import SQLiteKnowledgeStore
from tests.services.importance.test_scorer import NOW, inputs


@pytest.fixture
def repository(tmp_path):
    path = tmp_path / "knowledge.db"
    store = SQLiteKnowledgeStore(path)
    access = RepositoryAccessService(store)
    data = inputs()
    store.save_objects(data.objects)
    for row in data.analyses:
        access.save_content_analysis(row)
    access.save_trend_snapshots(data.trends, run=data.trend_run)
    yield path, store, access, data
    store.close()


def test_full_scoring_roundtrip_idempotence_and_read_context(repository):
    path, store, access, data = repository
    scorer = ImportanceScorer(access, None, ImportanceConfig(llm_top_n=0), clock=lambda: NOW)
    ids = [obj.id for obj in data.objects]
    first = scorer.score_batch(ids)
    assert all(row.context.matched_source_count == 5 for row in first)
    assert all(row.components["entity_importance"] == 1 for row in first)
    assert scorer.score_batch(list(reversed(ids))) == first
    assert (
        store.conn_manager.get_connection()
        .execute("SELECT count(*) FROM importance_scores")
        .fetchone()[0]
        == 100
    )
    store.close()
    reopened = SQLiteKnowledgeStore(path)
    try:
        assert (
            RepositoryAccessService(reopened).get_importance_score(first[0].knowledge_id)
            == first[0]
        )
    finally:
        reopened.close()


def test_rollback_on_late_failure_and_stale_run(repository):
    _, store, access, _ = repository
    scorer = ImportanceScorer(access, None, ImportanceConfig(llm_top_n=0), clock=lambda: NOW)
    scores = scorer.score_batch(["ko-0", "ko-1"])
    records = [row.model_dump(mode="json") for row in scores]
    records[0]["computed_at"] = (NOW + timedelta(seconds=1)).isoformat()
    records[1]["knowledge_id"] = "missing"
    with pytest.raises(LookupError):
        store.save_importance_scores(records)
    assert access.get_importance_score(scores[0].knowledge_id) == scores[0]
    records = [row.model_dump(mode="json") for row in scores]
    records[1]["computed_at"] = (NOW - timedelta(seconds=1)).isoformat()
    with pytest.raises(ValueError, match="newer"):
        store.save_importance_scores(records)
    assert access.get_importance_score(scores[0].knowledge_id) == scores[0]
    with pytest.raises(ValueError, match="Duplicate"):
        access.save_importance_scores([scores[0], scores[0]])
    store.delete_by_id("ko-0")
    assert access.get_importance_score("ko-0") is None
    with pytest.raises(LookupError):
        scorer.score_batch(["ko-0"])


def test_legacy_database_upgrade_is_repeatable_and_preserves_objects(tmp_path):
    path = tmp_path / "legacy.db"
    legacy = KNOWLEDGE_OBJECTS_DDL.replace(
        "    github_stars INTEGER CHECK (github_stars IS NULL OR github_stars >= 0),\n", ""
    )
    obj = inputs(1).objects[0].model_copy(update={"github_stars": None})
    with sqlite3.connect(path) as conn:
        conn.execute(legacy)
        conn.execute(
            "INSERT INTO knowledge_objects (id, source_type, source_name, external_id, "
            "content_hash, source_url, title, content_text, metadata_json, fetched_at, "
            "published_at, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                obj.id,
                obj.source_type,
                obj.source_name,
                obj.external_id,
                obj.content_hash,
                obj.source_url,
                obj.title,
                obj.content_text,
                obj.metadata.model_dump_json(),
                obj.fetched_at.isoformat(),
                obj.published_at.isoformat(),
                obj.created_at.isoformat(),
                obj.updated_at.isoformat(),
            ),
        )
    for _ in range(2):
        reopened = SQLiteKnowledgeStore(path)
        try:
            assert reopened.get_by_id(obj.id).github_stars is None
            assert reopened.get_by_id(obj.id).title == obj.title
            assert "importance_scores" in {
                row[0]
                for row in reopened.conn_manager.get_connection().execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
        finally:
            reopened.close()


def test_stars_survive_parser_standardization_builder_json_sqlite(tmp_path):
    raw = GitHubParser().parse_search_results(
        [
            {
                "full_name": "example/agent",
                "html_url": "https://github.com/example/agent",
                "description": "An AI agent",
                "stargazers_count": 321,
                "created_at": "2026-10-01T00:00:00Z",
            }
        ]
    )
    normalized = FieldMapper().map(DataStandardizer().standardize(raw))
    extraction = inputs(1).objects[0].metadata
    obj = ObjectBuilder().build(
        [EnrichedArticle(article=normalized[0], extraction=extraction, extraction_status="success")]
    )[0]
    assert raw[0].github_stars == normalized[0].github_stars == obj.github_stars == 321
    file = FileKnowledgeStore(tmp_path / "objects.json")
    file.save_objects([obj])
    assert file.save_objects([obj.model_copy(update={"github_stars": 322})]).updated == 1
    file = FileKnowledgeStore(tmp_path / "objects.json")
    loaded = file.get_by_id(obj.id)
    assert loaded.github_stars == 322
    store = SQLiteKnowledgeStore(tmp_path / "stars.db")
    try:
        store.save_objects([loaded])
        assert store.save_objects([loaded.model_copy(update={"github_stars": 0})]).updated == 1
        assert store.get_by_id(obj.id).github_stars == 0
        assert store.save_objects([loaded.model_copy(update={"github_stars": None})]).skipped == 1
        assert store.get_by_id(obj.id).github_stars == 0
    finally:
        store.close()


def test_window_boundaries_and_large_id_batch(repository):
    _, _, access, data = repository
    result = access.load_importance_inputs(
        [obj.id for obj in data.objects] + [f"absent-{i}" for i in range(450)],
        NOW - timedelta(days=7),
        NOW,
        "2026-W42",
    )
    assert len(result.objects) == 100 and len(result.analyses) == 100
    with pytest.raises(ValueError):
        access.load_importance_inputs([], NOW.replace(tzinfo=None), NOW, "2026-W42")
    with pytest.raises(ValueError):
        access.load_importance_inputs([], NOW - timedelta(days=7), NOW, "2026-W43")
