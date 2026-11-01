"""Real SQLite feedback, idempotency, score integration and transaction guarantees."""

import sqlite3
from unittest.mock import Mock

import pytest

from app.services.feedback.models import FeedbackRequest
from app.services.feedback.service import FeedbackService
from app.services.importance.config import ImportanceConfig
from app.services.importance.models import ImportanceScore, LLMImportanceScore
from app.services.importance.scorer import ImportanceScorer
from app.services.repository.access_service import RepositoryAccessService
from app.storage.knowledge.sqlite_store import SQLiteKnowledgeStore
from tests.services.importance.test_scorer import NOW, inputs


@pytest.fixture
def wired(tmp_path):
    store = SQLiteKnowledgeStore(tmp_path / "feedback.db")
    data = inputs(2)
    for obj in data.objects:
        obj.metadata.topics = [" AI ", "ai", "RAG"]
    store.save_objects(data.objects)
    access = RepositoryAccessService(store)
    service = FeedbackService(access)
    scorer = ImportanceScorer(access, None, ImportanceConfig(llm_top_n=0), clock=lambda: NOW)
    yield store, access, service, scorer
    store.close()


def test_set_repeat_switch_clear_and_rescore(wired):
    store, access, service, scorer = wired
    base = scorer.score_batch(["ko-0"])[0]
    positive = service.record_feedback("ko-0", FeedbackRequest(rating="useful"))
    assert positive.adjusted_score == pytest.approx(base.final_score + 0.1)
    assert service.record_feedback("ko-0", FeedbackRequest(rating="useful")) == positive
    assert service.get_feedback("ko-0") == positive
    assert scorer.score_batch(["ko-0"])[0].final_score == positive.adjusted_score
    negative = service.record_feedback("ko-0", FeedbackRequest(rating="not_useful"))
    assert negative.adjusted_score == pytest.approx(max(0, base.final_score - 0.1))
    current = access.get_importance_score("ko-0")
    assert current.feedback_rating == "not_useful" and current.score_version == "v2"
    assert current.rule_score == base.rule_score
    assert current.computed_at == base.computed_at
    cleared = service.record_feedback("ko-0", FeedbackRequest(rating=None))
    assert cleared.rating is None and cleared.updated_at is None
    assert cleared.adjusted_score == base.final_score
    assert service.record_feedback("ko-0", FeedbackRequest(rating=None)) == cleared
    assert (
        store.conn_manager.get_connection()
        .execute("SELECT count(*) FROM user_feedback")
        .fetchone()[0]
        == 0
    )


def test_feedback_before_scoring_and_preferences_ignore_deleted(wired):
    store, _, service, scorer = wired
    result = service.record_feedback("ko-0", FeedbackRequest(rating="useful"))
    assert result.base_score is None and result.adjusted_score is None
    service.record_feedback("ko-1", FeedbackRequest(rating="not_useful"))
    prefs = service.get_user_preferences()
    assert prefs.rated_items == 2
    assert [(p.topic, p.useful, p.not_useful) for p in prefs.topics] == [
        ("ai", 1, 1),
        ("rag", 1, 1),
    ]
    assert scorer.score_batch(["ko-0"])[0].feedback_rating == "useful"
    store.delete_by_id("ko-1")
    assert service.get_user_preferences().rated_items == 1
    with pytest.raises(LookupError):
        service.record_feedback("ko-1", FeedbackRequest(rating="useful"))
    with pytest.raises(LookupError):
        service.get_feedback("missing")
    store.delete_by_id("ko-1", permanent=True)
    assert (
        store.conn_manager.get_connection()
        .execute("SELECT count(*) FROM user_feedback WHERE knowledge_id='ko-1'")
        .fetchone()[0]
        == 0
    )


@pytest.mark.parametrize(
    "base,rating,expected", [(0.95, "useful", 1), (0.05, "not_useful", 0), (0.5, None, 0.5)]
)
def test_adjustment_is_bounded(base, rating, expected):
    assert FeedbackService.adjust_importance_score(base, rating) == expected


def test_feedback_during_refinement_wins_at_commit(wired):
    _, access, service, _ = wired
    provider = Mock()

    def refine(prompt, schema):
        service.record_feedback("ko-0", FeedbackRequest(rating="not_useful"))
        return LLMImportanceScore(knowledge_id="ko-0", score=0.9, reason="Evidence")

    provider.structured_chat.side_effect = refine
    scorer = ImportanceScorer(access, provider, ImportanceConfig(llm_top_n=1), clock=lambda: NOW)
    saved = scorer.score_batch(["ko-0"])[0]
    assert saved.feedback_rating == "not_useful"
    assert saved.final_score == pytest.approx(max(0, 0.7 * saved.rule_score + 0.3 * 0.9 - 0.1))
    assert saved == access.get_importance_score("ko-0")
    provider.structured_chat.assert_called_once()


def test_feedback_and_score_roll_back_together(wired):
    store, access, service, scorer = wired
    original = scorer.score_batch(["ko-0"])[0]
    conn = store.conn_manager.get_connection()
    conn.execute(
        "CREATE TRIGGER reject_score BEFORE UPDATE ON importance_scores "
        "BEGIN SELECT RAISE(ABORT, 'test failure'); END"
    )
    conn.commit()
    with pytest.raises(sqlite3.IntegrityError):
        service.record_feedback("ko-0", FeedbackRequest(rating="useful"))
    assert service.get_feedback("ko-0").rating is None
    assert access.get_importance_score("ko-0") == original


def test_upgrade_reopen_and_legacy_score_compatibility(wired):
    store, access, service, scorer = wired
    payload = scorer.score_batch(["ko-0"])[0].model_dump()
    payload.pop("feedback_rating")
    payload["score_version"] = "v1"
    assert ImportanceScore.model_validate(payload).feedback_rating is None
    conn = store.conn_manager.get_connection()
    conn.execute("DROP TABLE user_feedback")
    conn.commit()
    path = store.conn_manager.db_path
    store.close()
    reopened = SQLiteKnowledgeStore(path)
    try:
        service = FeedbackService(RepositoryAccessService(reopened))
        assert reopened.count() == 2
        saved = service.record_feedback("ko-0", FeedbackRequest(rating="useful"))
    finally:
        reopened.close()
    reopened = SQLiteKnowledgeStore(path)
    try:
        assert FeedbackService(RepositoryAccessService(reopened)).get_feedback("ko-0") == saved
    finally:
        reopened.close()
