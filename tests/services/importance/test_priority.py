"""Priority boundaries, independent digest policy and persisted-score evaluation."""

from datetime import datetime, timedelta, timezone
from math import nextafter
from unittest.mock import MagicMock

import pytest

from app.config.settings import Settings
from app.services.importance.config import ImportanceConfig
from app.services.importance.models import ImportanceScore, PriorityEvaluation, PriorityLevel
from app.services.importance.priority import PriorityEvaluator
from app.services.repository.access_service import RepositoryAccessService
from app.storage.knowledge.sqlite_store import SQLiteKnowledgeStore
from tests.fakes.analysis import make_analysis, make_knowledge

NOW = datetime(2026, 10, 28, tzinfo=timezone.utc)


def saved_score(knowledge_id="ko-0", score=0.65, llm_score=None):
    """Build a valid persisted score with an independently controlled final value."""
    config = ImportanceConfig(
        weight_relevance=1,
        weight_freshness=0,
        weight_authority=0,
        weight_github_stars=0,
        weight_cross_source=0,
        weight_entity=0,
        llm_top_n=0,
    )
    components = dict.fromkeys(config.weights, 0.0)
    components["relevance_score"] = score
    return ImportanceScore(
        knowledge_id=knowledge_id,
        computed_at=NOW,
        rule_score=score,
        final_score=score if llm_score is None else 0.7 * score + 0.3 * llm_score,
        components=components,
        component_status=dict.fromkeys(config.weights, "observed"),
        config=config,
        context={
            "window_start": NOW - timedelta(days=7),
            "window_end": NOW,
            "trend_week": "2026-W43",
            "observed_items": 1,
            "matched_source_count": 1,
            "entity_matches": [],
            "published_at": None,
            "source_label": "rss:a",
        },
        llm_adjusted=llm_score is not None,
        llm_score=llm_score,
        llm_reason="Refined evidence" if llm_score is not None else None,
    )


def evaluator(score=0.65, source_type="rss", source_name="a", **config):
    access = MagicMock(spec=RepositoryAccessService)
    access.get_importance_score.return_value = saved_score(score=score)
    access.get_knowledge_item.return_value = make_knowledge(
        make_analysis(source_type=source_type, source=source_name)
    )
    return PriorityEvaluator(access, ImportanceConfig(**config)), access


@pytest.mark.parametrize(
    ("score", "expected"),
    [
        (0.0, "ARCHIVE"),
        (nextafter(0.4, 0), "ARCHIVE"),
        (0.4, "LOW"),
        (nextafter(0.6, 0), "LOW"),
        (0.6, "MEDIUM"),
        (nextafter(0.75, 0), "MEDIUM"),
        (0.75, "HIGH"),
        (nextafter(0.9, 0), "HIGH"),
        (0.9, "CRITICAL"),
        (1.0, "CRITICAL"),
    ],
)
def test_exact_priority_boundaries(score, expected):
    service, access = evaluator(score)
    row = service.evaluate("ko-0")
    assert row.priority == PriorityLevel(expected)
    assert row.score == score and row.threshold_applied == row.priority.threshold
    assert row.digest_eligible is None
    assert repr(score) in row.reason and "computed_at=" in row.reason
    access.save_importance_scores.assert_not_called()


@pytest.mark.parametrize(
    ("source_type", "name", "mapping", "category", "threshold", "eligible"),
    [
        ("github", "a", {}, "github", 0.6, True),
        ("rss", "papers", {"rss:papers": "papers"}, "papers", 0.7, False),
        ("rss", "news", {"rss:news": "news"}, "news", 0.65, True),
        ("rss", "a:b / c", {"rss:a%3Ab%20%2F%20c": "papers"}, "papers", 0.7, False),
        ("huggingface", "a", {}, None, None, None),
        ("rss", "a", {}, None, None, None),
    ],
)
def test_digest_mapping_does_not_change_priority(
    source_type, name, mapping, category, threshold, eligible
):
    service, _ = evaluator(
        source_type=source_type, source_name=name, digest_source_categories=mapping
    )
    row = service.evaluate("ko-0")
    assert row.priority == PriorityLevel.MEDIUM and row.threshold_applied == 0.6
    assert (row.digest_category, row.digest_threshold, row.digest_eligible) == (
        category,
        threshold,
        eligible,
    )


def test_current_policy_and_final_refined_score_are_used():
    service, access = evaluator(source_type="github", threshold_github=0.95)
    access.get_importance_score.return_value = saved_score(score=1.0, llm_score=0.0)
    row = service.evaluate("ko-0")
    assert row.score == 0.7 and row.priority == PriorityLevel.MEDIUM
    assert row.digest_threshold == 0.95 and row.digest_eligible is False


def test_batch_order_deduplication_and_filter_inclusive_of_higher_bands():
    service, access = evaluator()
    scores = {"ko-0": 0.95, "ko-1": 0.75, "ko-2": 0.6}
    access.get_importance_score.side_effect = lambda key: saved_score(key, scores[key])
    access.get_knowledge_item.side_effect = lambda key: make_knowledge(
        make_analysis(index=int(key.split("-")[1]))
    )
    ids = ["ko-2", "ko-1", "ko-0", "ko-1"]
    assert [row.knowledge_id for row in service.evaluate_batch(ids)] == ids[:3]
    assert access.get_importance_score.call_count == 3
    assert service.filter_by_priority(ids, PriorityLevel.HIGH) == ["ko-1", "ko-0"]
    assert service.filter_by_priority(ids, PriorityLevel.ARCHIVE) == ids[:3]
    access.reset_mock()
    assert service.evaluate_batch([]) == []
    assert service.filter_by_priority([], PriorityLevel.HIGH) == []
    assert not access.mock_calls
    with pytest.raises(ValueError):
        service.filter_by_priority(ids, "urgent")
    assert not access.mock_calls


@pytest.mark.parametrize("ids", ["ko-0", b"ko-0", ["ko-0", " "], [42], None])
def test_bad_batch_input_fails_before_reads(ids):
    service, access = evaluator()
    with pytest.raises(ValueError):
        service.evaluate_batch(ids)
    assert not access.mock_calls


def test_missing_score_deleted_item_and_mismatched_identity():
    service, access = evaluator()
    for value in ("", " ", None, 42):
        with pytest.raises(ValueError):
            service.evaluate(value)
    assert not access.mock_calls
    access.get_importance_score.return_value = None
    with pytest.raises(LookupError, match="No saved importance"):
        service.evaluate("ko-0")
    access.get_importance_score.return_value = saved_score()
    access.get_knowledge_item.return_value = None
    with pytest.raises(LookupError, match="missing or deleted"):
        service.evaluate("ko-0")
    access.get_knowledge_item.return_value = make_knowledge(make_analysis(1))
    with pytest.raises(ValueError, match="another knowledge_id"):
        service.evaluate("ko-0")


@pytest.mark.parametrize(
    "mapping",
    [
        {"rss": "news"},
        {"rss:a:b": "news"},
        {"rss:a b": "news"},
        {"rss:": "news"},
        {"rss:a": "unknown"},
        {"github:a": "papers"},
    ],
)
def test_invalid_digest_mapping_is_rejected(mapping):
    with pytest.raises(ValueError):
        ImportanceConfig(digest_source_categories=mapping)


@pytest.mark.parametrize(
    "changes",
    [
        {"score": float("nan")},
        {"score": float("inf")},
        {"score": -0.1},
        {"score": 1.1},
        {"priority": "HIGH"},
        {"threshold_applied": 0.65},
        {"digest_eligible": False},
        {"digest_threshold": 0.65},
        {"digest_category": "news"},
        {"digest_category": "news", "digest_threshold": 0.65, "digest_eligible": False},
    ],
)
def test_evaluation_model_rejects_contradictions(changes):
    service, _ = evaluator()
    payload = service.evaluate("ko-0").model_dump()
    with pytest.raises(ValueError):
        PriorityEvaluation.model_validate({**payload, **changes})


def test_settings_json_loads_digest_policy(monkeypatch):
    monkeypatch.setenv("IMPORTANCE", '{"digest_source_categories":{"rss:a":"papers"}}')
    values = dict.fromkeys(
        [
            "groq_api_key",
            "cohere_api_key",
            "qdrant_url",
            "qdrant_api_key",
            "zalo_app_id",
            "zalo_app_secret",
            "zalo_access_token",
            "zalo_webhook_secret",
        ],
        "test",
    )
    settings = Settings(_env_file=None, **values)
    assert settings.importance.digest_source_categories == {"rss:a": "papers"}


def test_sqlite_round_trip_is_read_only_and_old_config_remains_readable(tmp_path):
    store = SQLiteKnowledgeStore(tmp_path / "knowledge.db")
    try:
        store.save_objects([make_knowledge(make_analysis())])
        access = RepositoryAccessService(store)
        payload = saved_score().model_dump(mode="json")
        payload["config"].pop("digest_source_categories")
        store.save_importance_scores([payload])
        connection = store.conn_manager.get_connection()
        before = connection.total_changes
        service = PriorityEvaluator(
            access, ImportanceConfig(digest_source_categories={"rss:a": "papers"})
        )
        row = service.evaluate("ko-0")
        assert row.priority == PriorityLevel.MEDIUM and row.digest_eligible is False
        assert service.evaluate("ko-0") == row
        with pytest.raises(LookupError):
            service.evaluate_batch(["ko-0", "absent"])
        assert connection.total_changes == before
        assert access.get_importance_score("ko-0").final_score == 0.65
        store.delete_by_id("ko-0")
        with pytest.raises(LookupError):
            service.evaluate("ko-0")
    finally:
        store.close()
