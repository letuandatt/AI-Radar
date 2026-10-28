"""Assessment formula, missing evidence, retrieval errors and complete pagination."""

from datetime import timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.services.importance.models import RelevanceAssessment
from app.services.importance.relevance import RelevanceAssessor
from app.services.repository.access_service import RepositoryAccessService
from app.services.repository.query_models import (
    KnowledgeDetailResponse,
    KnowledgeListResponse,
    PageInfo,
    PaginationMode,
)
from app.services.retrieval.retrieval_models import (
    RetrievalResponse,
    RetrievalResult,
    RetrievalServiceUnavailableError,
)
from app.services.retrieval.retrieval_service import RetrievalService
from app.storage.knowledge.sqlite_store import SQLiteKnowledgeStore
from tests.fakes.analysis import make_analysis, make_knowledge
from tests.services.importance.test_priority import NOW, saved_score


def neighbor(key="neighbor", topics=None):
    return RetrievalResult(
        knowledge_id=key,
        title=key,
        topics=["RAG"] if topics is None else topics,
        relevance_score=999.0,
    )


def response(rows):
    return RetrievalResponse(query="related", results=rows, total_matches=len(rows))


def detail(key="ko-0", topics=None):
    return KnowledgeDetailResponse(
        id=key,
        title=key,
        source_type="rss",
        source_name="a",
        content_text="AI",
        content_hash=key,
        metadata={"topics": ["RAG", "LLM"] if topics is None else topics},
    )


def setup(topics=None, rows=None):
    access = MagicMock(spec=RepositoryAccessService)
    retrieval = MagicMock(spec=RetrievalService)
    access.get_importance_score.return_value = saved_score(score=0.8, llm_score=0)
    access.get_knowledge_item.return_value = detail(topics=topics)
    retrieval.get_related_items.return_value = response([neighbor()] if rows is None else rows)
    return RelevanceAssessor(access, retrieval, clock=lambda: NOW), access, retrieval


def test_jaccard_normalization_mean_and_saved_component_not_final_score():
    service, access, retrieval = setup(
        topics=[" RAG ", "rag", " LLM", " "],
        rows=[
            neighbor("ko-0"),
            neighbor("b", ["rag"]),
            neighbor("b", ["LLM"]),
            neighbor("c", ["vision"]),
            neighbor("d", []),
        ],
    )
    row = service.assess("ko-0")
    assert row.base_relevance == 0.8
    assert row.topic_consistency == 0.25
    assert row.relevance_score == pytest.approx(0.635)
    assert row.related_items == ["b", "c", "d"]
    assert row.status == "assessed" and row.assessed_at == NOW
    assert "2 usable neighbors" in row.reason
    retrieval.get_related_items.assert_called_once_with("ko-0", top_k=5)
    access.save_importance_scores.assert_not_called()
    assert RelevanceAssessor._topics(["Large   Language\tModel"]) == {"large language model"}


@pytest.mark.parametrize(
    ("topics", "rows", "consistency", "status", "expected"),
    [
        (["RAG"], [], None, "insufficient_context", 0.8),
        ([], [neighbor()], None, "insufficient_context", 0.8),
        (["RAG"], [neighbor(topics=[])], None, "insufficient_context", 0.8),
        (["RAG"], [neighbor(topics=["vision"])], 0, "assessed", 0.56),
        (["RAG"], [neighbor(topics=["rag"])], 1, "assessed", 0.86),
    ],
)
def test_unknown_context_is_distinct_from_zero_overlap(topics, rows, consistency, status, expected):
    service, _, _ = setup(topics, rows)
    result = service.assess("ko-0")
    assert result.topic_consistency == consistency and result.status == status
    assert result.relevance_score == pytest.approx(expected)


def test_top_five_unique_neighbors_and_order():
    service, _, _ = setup(rows=[neighbor("ko-0")] + [neighbor(str(i)) for i in range(8)])
    assert service.assess("ko-0").related_items == [str(i) for i in range(5)]


def test_missing_score_item_identity_or_base_fails_before_retrieval():
    service, access, retrieval = setup()
    access.get_importance_score.return_value = None
    with pytest.raises(LookupError):
        service.assess("ko-0")
    access.get_importance_score.return_value = saved_score()
    access.get_knowledge_item.return_value = None
    with pytest.raises(LookupError):
        service.assess("ko-0")
    access.get_knowledge_item.return_value = detail("wrong")
    with pytest.raises(ValueError, match="another knowledge_id"):
        service.assess("ko-0")
    access.get_knowledge_item.return_value = detail()
    invalid = saved_score(score=0)
    invalid.component_status["relevance_score"] = "missing"
    access.get_importance_score.return_value = invalid
    with pytest.raises(ValueError, match="must be observed"):
        service.assess("ko-0")
    retrieval.get_related_items.assert_not_called()


def test_retrieval_failure_propagates_and_naive_clock_is_rejected():
    service, access, retrieval = setup()
    error = RetrievalServiceUnavailableError("Vector not found")
    retrieval.get_related_items.side_effect = error
    with pytest.raises(RetrievalServiceUnavailableError) as caught:
        service.assess("ko-0")
    assert caught.value is error
    with pytest.raises(ValueError, match="timezone-aware"):
        RelevanceAssessor(access, retrieval, clock=lambda: NOW.replace(tzinfo=None)).assess("ko-0")


@pytest.mark.parametrize("ids", ["ko-0", b"ko-0", ["ko-0", " "], [42], None])
def test_invalid_batch_fails_before_io(ids):
    service, access, retrieval = setup()
    with pytest.raises(ValueError):
        service.assess_batch(ids)
    assert not access.mock_calls and not retrieval.mock_calls


def test_batch_deduplicates_in_input_order_and_empty_does_no_io():
    service, access, retrieval = setup()
    assert service.assess_batch([]) == []
    assert not access.mock_calls and not retrieval.mock_calls
    access.get_importance_score.side_effect = lambda key: saved_score(key)
    access.get_knowledge_item.side_effect = lambda key: detail(key)
    assert [row.knowledge_id for row in service.assess_batch(["b", "a", "b"])] == ["b", "a"]
    assert retrieval.get_related_items.call_count == 2


@pytest.mark.parametrize("threshold", [-0.1, 1.1, float("nan"), float("inf"), True])
def test_invalid_scan_threshold_fails_before_io(threshold):
    service, access, retrieval = setup()
    with pytest.raises(ValueError):
        service.find_irrelevant_items(threshold)
    assert not access.mock_calls and not retrieval.mock_calls


def test_scan_excludes_unknown_and_uses_strict_threshold():
    service, access, retrieval = setup()
    access.search_knowledge.return_value = KnowledgeListResponse(
        items=[
            SimpleNamespace(
                id=key, title=key, source_type="rss", source_name="a", content_hash=key
            ).__dict__
            for key in ["low", "edge", "unknown"]
        ],
        total=3,
        page_info=PageInfo(has_next=False),
    )
    access.get_importance_score.side_effect = lambda key: saved_score(
        key, 0.2 if key != "edge" else 0
    )
    access.get_knowledge_item.side_effect = lambda key: detail(key, ["RAG"])
    retrieval.get_related_items.side_effect = lambda key, top_k: response(
        [] if key == "unknown" else [neighbor(topics=["RAG"] if key == "edge" else ["vision"])]
    )
    assert service.find_irrelevant_items(0.3) == ["low"]


def test_real_sqlite_scan_reads_every_page_with_equal_timestamps(tmp_path):
    store = SQLiteKnowledgeStore(tmp_path / "knowledge.db")
    try:
        objects = [make_knowledge(make_analysis(i)) for i in range(205)]
        for obj in objects:
            obj.created_at = NOW
        store.save_objects(objects)
        store.save_importance_scores(
            [saved_score(obj.id, 0.2).model_dump(mode="json") for obj in objects]
        )
        access = RepositoryAccessService(store)
        retrieval = MagicMock(spec=RetrievalService)
        retrieval.get_related_items.return_value = response([neighbor(topics=["unrelated"])])
        service = RelevanceAssessor(access, retrieval, clock=lambda: NOW)
        before = store.conn_manager.get_connection().total_changes
        assert set(service.find_irrelevant_items()) == {obj.id for obj in objects}
        assert retrieval.get_related_items.call_count == 205
        assert store.conn_manager.get_connection().total_changes == before
    finally:
        store.close()


def test_scan_empty_and_broken_pagination_fail_explicitly():
    service, access, _ = setup()
    access.search_knowledge.return_value = KnowledgeListResponse(total=0, page_info=PageInfo())
    assert service.find_irrelevant_items() == []
    query = access.search_knowledge.call_args.args[0]
    assert query.pagination_mode == PaginationMode.PAGE
    for total, has_next in [(1, True), (1, False), (None, False)]:
        access.search_knowledge.return_value = KnowledgeListResponse(
            total=total, page_info=PageInfo(has_next=has_next)
        )
        with pytest.raises(RuntimeError):
            service.find_irrelevant_items()


@pytest.mark.parametrize(
    "changes",
    [
        {"relevance_score": float("nan")},
        {"base_relevance": 1.1},
        {"topic_consistency": -1},
        {"relevance_score": 0.1},
        {"topic_consistency": None},
        {"related_items": []},
        {"related_items": ["ko-0"]},
        {"related_items": ["x", "x"]},
        {"status": "insufficient_context"},
        {"assessed_at": NOW.replace(tzinfo=None)},
    ],
)
def test_model_rejects_contradictory_assessments(changes):
    service, _, _ = setup()
    payload = service.assess("ko-0").model_dump()
    with pytest.raises(ValueError):
        RelevanceAssessment.model_validate({**payload, **changes})


def test_assessment_json_roundtrip_has_utc_time():
    service, _, _ = setup()
    row = service.assess("ko-0")
    assert row.assessed_at.tzinfo == timezone.utc
    assert RelevanceAssessment.model_validate_json(row.model_dump_json()) == row


@pytest.mark.parametrize("second_total", [2, 3])
def test_scan_rejects_repeated_ids_or_changing_count(second_total):
    service, access, _ = setup()
    item = {
        "id": "ko-0",
        "title": "item",
        "source_type": "rss",
        "source_name": "a",
        "content_hash": "hash",
    }
    access.search_knowledge.side_effect = [
        KnowledgeListResponse(items=[item], total=2, page_info=PageInfo(has_next=True)),
        KnowledgeListResponse(items=[item], total=second_total, page_info=PageInfo()),
    ]
    with pytest.raises(RuntimeError):
        service.find_irrelevant_items()
    assert access.search_knowledge.call_args.args[0].offset == 1
