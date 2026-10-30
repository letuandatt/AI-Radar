"""Digest contracts over real SQLite; no external providers or network calls."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from time import perf_counter
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.config.importance import ImportanceConfig
from app.services.digest.config import DigestConfig
from app.services.digest.generator import DailyDigestGenerator
from app.services.digest.models import DailyDigest
from app.services.intelligence.models import IntelligenceDocument
from app.services.repository.access_service import RepositoryAccessService
from app.services.repository.bootstrap import create_digest_service
from app.storage.knowledge.sqlite_store import SQLiteKnowledgeStore
from tests.fakes.analysis import make_analysis, make_knowledge
from tests.services.intelligence.conftest import DAY, NOW
from tests.services.intelligence.conftest import environment as environment
from tests.services.intelligence.test_refiner import prepared as prepared


@pytest.fixture
def digest_env(environment, prepared):
    store, access, _, _ = environment
    document, refiner, provider = prepared
    refined = refiner.refine(document)
    access.save_intelligence_document(refined)
    conn = store._conn_manager.get_connection()
    with conn:
        conn.execute("UPDATE knowledge_objects SET published_at=?", (DAY + "T12:00:00+00:00",))
    config = DigestConfig(
        importance=ImportanceConfig(
            digest_source_categories={"rss:a": "news"},
            threshold_news=0,
        )
    )
    generator = DailyDigestGenerator(access, config, clock=lambda: NOW + timedelta(seconds=2))
    return store, access, refined, generator, config


def test_generate_cache_roundtrip_and_no_provider_calls(digest_env, monkeypatch):
    store, access, doc, generator, config = digest_env
    spy = MagicMock(wraps=access.save_digest)
    monkeypatch.setattr(access, "save_digest", spy)
    result = generator.generate(DAY)
    assert result.total_items == result.eligible_count == result.candidate_count == 3
    assert result.sections[0].category == "news"
    assert result.topic_groups == {"RAG": ["ko-0", "ko-1", "ko-2"]}
    assert result.intelligence == doc
    assert DailyDigest.model_validate_json(result.model_dump_json()) == result
    spy.assert_called_once()
    monkeypatch.setattr(access, "load_digest_inputs", MagicMock(side_effect=AssertionError))
    assert generator.generate(DAY) == result
    assert generator.get_digest(DAY) == result
    assert generator.get_digest_history() == [DAY]
    assert generator.get_digest("2026-10-19") is None


def test_limits_thresholds_categories_and_performance(digest_env):
    store, access, _, _, _ = digest_env
    base = access.get_importance_score("ko-0")
    objects, scores = [], []
    for i in range(1000):
        source_type = "github" if i % 4 == 0 else "rss"
        source = ["gh", "papers", "news", "other"][i % 4]
        analysis = make_analysis(i + 10, source=source, source_type=source_type, at=NOW)
        obj = make_knowledge(analysis).model_copy(
            update={
                "published_at": NOW - timedelta(days=1),
                "fetched_at": NOW - timedelta(days=1),
            }
        )
        value = 0.8 if i % 2 else 0.7
        objects.append(obj)
        scores.append(
            base.model_copy(
                update={
                    "knowledge_id": obj.id,
                    "rule_score": value,
                    "final_score": value,
                    "components": {key: value for key in base.components},
                    "component_status": {key: "observed" for key in base.components},
                }
            )
        )
    store.save_objects(objects)
    access.save_importance_scores(scores)
    for i, obj in enumerate(objects):
        access.save_content_analysis(make_analysis(i + 10, at=NOW))
    config = DigestConfig(
        importance=ImportanceConfig(
            digest_source_categories={"rss:papers": "papers", "rss:news": "news"},
            threshold_github=0.7,
            threshold_news=0.71,
            threshold_papers=0.8,
        ),
        others_threshold=0.8,
    )
    generator = DailyDigestGenerator(access, config, clock=lambda: NOW + timedelta(seconds=2))
    start = perf_counter()
    result = generator.generate(DAY)
    assert perf_counter() - start < 5
    assert result.candidate_count == 1003
    assert result.eligible_count == 750
    assert result.total_items == 15
    assert {s.category for s in result.sections} == {"papers", "github", "others"}
    assert all(len(s.items) == 5 for s in result.sections)
    assert all(
        s.items == sorted(s.items, key=lambda i: (-i.importance_score, i.knowledge_id))
        for s in result.sections
    )
    assert set(sum(result.topic_groups.values(), [])) == {
        i.knowledge_id for s in result.sections for i in s.items
    }


def test_unknown_mapping_empty_is_cached(digest_env):
    _, access, _, _, _ = digest_env
    service = DailyDigestGenerator(access, DigestConfig(), clock=lambda: NOW + timedelta(seconds=2))
    result = service.generate(DAY)
    assert result.total_items == result.eligible_count == 0
    assert result.unmapped_count == 3
    assert result.sections == [] and result.topic_groups == {}
    assert service.generate(DAY) == result


@pytest.mark.parametrize(
    "stamp,count",
    [
        ("2026-10-20T00:00:00+00:00", 3),
        ("2026-10-21T00:00:00+00:00", 0),
        ("2026-10-19T23:59:59.999999+00:00", 0),
        ("2026-10-21T06:59:59.999999+07:00", 3),
        ("2026-10-20T12:00:00", 3),
    ],
)
def test_exact_utc_boundaries(digest_env, stamp, count):
    store, _, _, generator, _ = digest_env
    with store._conn_manager.get_connection() as conn:
        conn.execute("UPDATE knowledge_objects SET published_at=?", (stamp,))
    result = generator.generate(DAY)
    assert result.total_items == count
    if count and "+" not in stamp:
        assert all(i.assumed_utc for s in result.sections for i in s.items)


def test_missing_publication_uses_fetched_without_faking_date(digest_env):
    store, _, _, generator, _ = digest_env
    with store._conn_manager.get_connection() as conn:
        conn.execute("UPDATE knowledge_objects SET published_at=NULL")
    result = generator.generate(DAY)
    assert result.total_items == 3
    assert all(
        i.published_at is None and i.date_basis == "fetched_at"
        for s in result.sections
        for i in s.items
    )


@pytest.mark.parametrize(
    "table", ["content_analyses", "importance_scores", "intelligence_documents"]
)
def test_missing_prerequisites_preserve_cached_digest(digest_env, table):
    store, access, _, generator, _ = digest_env
    old = generator.generate(DAY)
    with store._conn_manager.get_connection() as conn:
        conn.execute(f"DELETE FROM {table}")
    assert generator.generate(DAY) == old
    with pytest.raises(LookupError):
        generator.generate(DAY, rebuild=True)
    assert access.get_digest(DAY) == old


def test_changed_inputs_fail_before_replacement(digest_env, monkeypatch):
    store, access, _, generator, _ = digest_env
    old = generator.generate(DAY)
    save = access.save_digest

    def changed(digest, **options):
        with store._conn_manager.get_connection() as conn:
            conn.execute("UPDATE knowledge_objects SET content_text='updated'")
        return save(digest, **options)

    monkeypatch.setattr(access, "save_digest", changed)
    with pytest.raises(RuntimeError, match="prerequisites changed"):
        generator.generate(DAY, rebuild=True)
    assert access.get_digest(DAY) == old


def test_sql_failure_rolls_back_rebuild(digest_env):
    store, access, _, generator, _ = digest_env
    old = generator.generate(DAY)
    with store._conn_manager.get_connection() as conn:
        conn.execute(
            "CREATE TRIGGER reject_digest BEFORE UPDATE ON daily_digests "
            "BEGIN SELECT RAISE(ABORT, 'forced'); END"
        )
    with pytest.raises(Exception, match="forced"):
        generator.generate(DAY, rebuild=True)
    assert access.get_digest(DAY) == old


def test_rebuild_and_compare_and_swap(digest_env):
    _, access, _, generator, _ = digest_env
    first = generator.generate(DAY)
    data = access.load_digest_inputs(DAY)
    second = generator.generate(DAY, rebuild=True)
    assert second.digest_id != first.digest_id
    assert access.get_digest(DAY) == second
    with pytest.raises(RuntimeError, match="Digest changed"):
        access.save_digest(
            first, fingerprint=data["fingerprint"], rebuild=True, expected_id=first.digest_id
        )


def test_concurrent_normal_generation_returns_one_winner(digest_env, tmp_path):
    store, access, _, generator, config = digest_env
    # Separate store/connection instances exercise SQLite serialization too.
    other = SQLiteKnowledgeStore(store._conn_manager.db_path)
    try:
        service = DailyDigestGenerator(
            RepositoryAccessService(other), config, clock=lambda: NOW + timedelta(seconds=2)
        )
        with ThreadPoolExecutor(max_workers=2) as pool:
            rows = list(pool.map(lambda g: g.generate(DAY), [generator, service]))
        assert rows[0] == rows[1] == access.get_digest(DAY)
    finally:
        other.close()


def test_document_validation_idempotency_and_archive_snapshot(digest_env):
    store, access, doc, generator, _ = digest_env
    assert access.get_intelligence_document(DAY) == doc
    access.save_intelligence_document(doc)
    old = generator.generate(DAY)
    unrefined = doc.model_copy(update={"refined_at": None})
    with pytest.raises(ValueError, match="refinement"):
        access.save_intelligence_document(unrefined)
    invalid = doc.model_copy(deep=True)
    invalid.sections[0].content = "Uncited replacement"
    with pytest.raises(ValueError, match="blocks"):
        access.save_intelligence_document(invalid)
    newer = doc.model_copy(update={"document_id": "new", "refined_at": NOW + timedelta(seconds=2)})
    access.save_intelligence_document(newer)
    with pytest.raises(ValueError, match="newer"):
        access.save_intelligence_document(doc)
    assert access.get_digest(DAY).intelligence == old.intelligence
    assert generator.generate(DAY, rebuild=True).intelligence.document_id == "new"
    with store._conn_manager.get_connection() as conn:
        conn.execute("UPDATE knowledge_objects SET source_url='https://changed.example'")
    with pytest.raises(ValueError, match="citation changed"):
        access.save_intelligence_document(newer)
    with pytest.raises(ValueError, match="citation changed"):
        generator.generate(DAY, rebuild=True)


@pytest.mark.parametrize("date", ["2026-1-1", "bad", "2026-10-30"])
def test_invalid_and_future_dates(digest_env, date):
    with pytest.raises(ValueError):
        digest_env[3].generate(date)


@pytest.mark.parametrize("limit", [True, 0, -1, 3651, 1.5])
def test_history_limit_validation(digest_env, limit):
    with pytest.raises(ValueError):
        digest_env[3].get_digest_history(limit)


def test_history_order_and_future_items(digest_env):
    store, access, doc, generator, _ = digest_env
    generator.generate(DAY)
    data = doc.model_dump()
    data["date"] = "2026-10-19"
    for section in data["sections"]:
        for insight in section["insights"]:
            insight["report_date"] = "2026-10-19"
    access.save_intelligence_document(IntelligenceDocument.model_validate(data))
    generator.generate("2026-10-19")
    assert generator.get_digest_history() == [DAY, "2026-10-19"]
    assert generator.get_digest_history(1) == [DAY]


def test_factory_and_registry_initializer(digest_env, monkeypatch):
    from app.core import application

    store, _, _, _, config = digest_env
    settings = SimpleNamespace(importance=config.importance)
    initializer = SimpleNamespace(sqlite_store=store)
    service = create_digest_service(initializer, settings)
    assert isinstance(service, DailyDigestGenerator)
    registry = MagicMock()
    registry.get_component.return_value = initializer
    monkeypatch.setattr(application, "_registry", registry)
    monkeypatch.setattr(application, "get_settings", lambda: settings)
    assert isinstance(application._init_digest(), DailyDigestGenerator)
    registry.get_component.assert_called_once_with("repository")


def test_model_rejects_wrong_totals_topics_day_and_policy(digest_env):
    _, _, _, generator, _ = digest_env
    good = generator.generate(DAY)
    changes = [
        {"total_items": 100},
        {"topic_groups": {"fake": ["absent"]}},
        {"digest_date": "2026-10-19"},
        {"unmapped_count": 10},
        {"config": DigestConfig().model_dump()},
    ]
    for change in changes:
        with pytest.raises(ValueError):
            DailyDigest.model_validate({**good.model_dump(), **change})


def test_rebuild_detects_document_replacement(digest_env, monkeypatch):
    _, access, doc, generator, _ = digest_env
    old = generator.generate(DAY)
    original_save = access.save_digest

    def replace_document(digest, **options):
        access.save_intelligence_document(
            doc.model_copy(
                update={
                    "document_id": "replacement",
                    "refined_at": NOW + timedelta(seconds=2),
                }
            )
        )
        return original_save(digest, **options)

    monkeypatch.setattr(access, "save_digest", replace_document)
    with pytest.raises(RuntimeError, match="prerequisites changed"):
        generator.generate(DAY, rebuild=True)
    assert access.get_digest(DAY) == old


def test_future_publication_is_not_selected(digest_env):
    store, access, doc, _, config = digest_env
    today = NOW.date().isoformat()
    data = doc.model_dump()
    data["date"] = today
    for section in data["sections"]:
        for insight in section["insights"]:
            insight["report_date"] = today
    access.save_intelligence_document(IntelligenceDocument.model_validate(data))
    with store._conn_manager.get_connection() as conn:
        conn.execute(
            "UPDATE knowledge_objects SET published_at=?", ((NOW + timedelta(hours=1)).isoformat(),)
        )
    result = DailyDigestGenerator(
        access, config, clock=lambda: NOW + timedelta(seconds=2)
    ).generate(today)
    assert result.candidate_count == result.total_items == 0
