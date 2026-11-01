"""Generation contract, persistence, provenance and failure atomicity."""

import html
import json
from datetime import timedelta
from time import perf_counter
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from app.core import application
from app.services.intelligence.insight_generator import InsightGenerator
from app.services.intelligence.models import InsightBatch, InsightDraft, day_start
from app.services.repository.bootstrap import create_intelligence_service
from app.services.trend.models import trend_identity
from tests.services.intelligence.conftest import DAY, NOW, draft


def test_ten_insights_real_storage_and_mock_performance(environment):
    _, access, provider, generator = environment
    provider.structured_chat.return_value = InsightBatch(
        insights=[draft(title=f"Finding {i}") for i in range(10)]
    )
    start = perf_counter()
    with patch.object(access, "save_insights", wraps=access.save_insights) as save:
        rows = generator.generate_insights(DAY)
    assert perf_counter() - start < 30
    save.assert_called_once()
    assert len(rows) == 10 and len({row.insight_id for row in rows}) == 10
    assert access.read_insight_report(DAY)[0].insight_count == 10
    for row in rows:
        assert row.report_date == DAY and row.generated_at == NOW
        assert len(set(row.evidence_ids)) == 2 and 0 <= row.confidence <= 1
        for citation in row.citations:
            assert (
                citation.source_url == access.get_knowledge_item(citation.knowledge_id).source_url
            )
    assert len(generator.get_insights_by_type("connection", 3)) == 3
    assert len(access.list_insights(DAY, "connection")) == 10


@pytest.mark.parametrize(
    "change",
    [
        {"evidence_ids": ["ko-0", "ko-0"]},
        {"confidence": -0.1},
        {"confidence": 1.1},
        {"confidence": float("nan")},
        {"evidence_ids": ["ko-0"]},
        {"title": " "},
    ],
)
def test_invalid_provider_construct_preserves_old_report(environment, change):
    _, access, provider, generator = environment
    generator.generate_insights(DAY)
    before = access.read_insight_report(DAY)
    invalid = InsightDraft.model_construct(**(draft().model_dump() | change))
    provider.structured_chat.return_value = InsightBatch.model_construct(insights=[invalid])
    with pytest.raises(ValidationError):
        generator.generate_insights(DAY)
    assert access.read_insight_report(DAY) == before


@pytest.mark.parametrize(
    "changes",
    [
        {"evidence_ids": ["ko-0", "invented"]},
        {"insight_type": "trend", "signal_ids": ["invented"]},
        {
            "insight_type": "trend",
            "signal_ids": [trend_identity("topic", "rag")],
            "evidence_ids": ["ko-0", "ko-2"],
        },
        {"insight_type": "pattern", "signal_ids": [trend_identity("topic", "rag")]},
    ],
)
def test_unknown_and_wrong_signal_evidence_fails_before_write(environment, changes):
    _, access, provider, generator = environment
    provider.structured_chat.return_value = InsightBatch(insights=[draft(**changes)])
    with pytest.raises(ValueError):
        generator.generate_insights(DAY)
    assert access.read_insight_report(DAY) == (None, [])


def test_persisted_trend_support_and_prompt_scope(environment):
    _, access, provider, generator = environment
    provider.structured_chat.return_value = InsightBatch(
        insights=[draft(insight_type="trend", signal_ids=[trend_identity("topic", "rag")])]
    )
    assert generator.generate_insights(DAY)[0].insight_type == "trend"
    prompt = provider.structured_chat.call_args.args[0]
    data = json.loads(
        html.unescape(prompt.split("<untrusted_data>\n")[1].split("\n</untrusted_data>")[0])
    )
    assert data["report_date"] == DAY and data["daily_candidates"] == 3
    assert data["signals"][0]["week"] == "2026-W42"


def test_empty_rerun_replaces_old_rows_and_latest_day_semantics(environment):
    _, access, provider, generator = environment
    generator.generate_insights(DAY)
    provider.structured_chat.return_value = InsightBatch(insights=[])
    generator.generate_insights(DAY)
    run, rows = access.read_insight_report(DAY)
    assert run.insight_count == 0 and rows == []
    assert generator.get_insights_by_type("connection") == []
    assert access.read_insight_report("2026-10-19") == (None, [])


def test_provider_error_and_deleted_source_preserve_previous_report(environment):
    store, access, provider, generator = environment
    generator.generate_insights(DAY)
    before = access.read_insight_report(DAY)
    provider.structured_chat.side_effect = RuntimeError("provider failed")
    with pytest.raises(RuntimeError, match="provider failed"):
        generator.generate_insights(DAY)
    assert access.read_insight_report(DAY) == before

    def remove(*args):
        store.delete_by_id("ko-0")
        return InsightBatch(insights=[draft()])

    provider.structured_chat.side_effect = remove
    with pytest.raises(LookupError, match="Citation no longer exists"):
        generator.generate_insights(DAY)
    assert access.read_insight_report(DAY) == before


def test_missing_prerequisites_do_not_call_llm(environment):
    store, access, provider, generator = environment
    with store._conn_manager.get_connection() as conn:
        conn.execute("DELETE FROM importance_scores WHERE knowledge_id = 'ko-0'")
    with pytest.raises(LookupError, match="Missing saved"):
        generator.generate_insights(DAY)
    provider.structured_chat.assert_not_called()
    assert access.read_insight_report(DAY) == (None, [])


def test_missing_trend_run_fails_but_empty_run_is_valid(environment):
    store, access, provider, generator = environment
    with store._conn_manager.get_connection() as conn:
        conn.execute("DELETE FROM trend_snapshots")
        conn.execute("DELETE FROM trend_runs")
    with pytest.raises(LookupError, match="No identification run"):
        generator.generate_insights(DAY)
    provider.structured_chat.assert_not_called()


def test_stale_write_and_failed_sql_insert_roll_back(environment):
    _, access, _, generator = environment
    generator.generate_insights(DAY)
    run, rows = access.read_insight_report(DAY)
    before = (run, rows)
    with pytest.raises(ValueError, match="newer insight run"):
        access.save_insights(
            rows, run=run.model_copy(update={"started_at": NOW - timedelta(seconds=1)})
        )
    assert access.read_insight_report(DAY) == before
    with pytest.raises(ValueError, match="count/identities"):
        access.save_insights(rows * 2, run=run)
    assert access.read_insight_report(DAY) == before


@pytest.mark.parametrize("date", ["2026-1-01", "2026-02-30", "not-date", "2026-10-22"])
def test_invalid_or_future_report_date(environment, date):
    _, _, provider, generator = environment
    with pytest.raises(ValueError):
        generator.generate_insights(date)
    provider.structured_chat.assert_not_called()


@pytest.mark.parametrize("limit", [0, 11, True, 1.5])
def test_limit_validation(environment, limit):
    with pytest.raises(ValueError):
        environment[3].get_insights_by_type("connection", limit)


def test_utc_date_boundary_and_candidate_cap(environment):
    store, access, _, _ = environment
    with store._conn_manager.get_connection() as conn:
        conn.execute(
            "UPDATE knowledge_objects SET fetched_at=? WHERE id='ko-0'",
            ("2026-10-21T00:00:00+00:00",),
        )
        conn.execute(
            "UPDATE knowledge_objects SET fetched_at=? WHERE id='ko-1'",
            ("2026-10-20T23:59:59.999999+00:00",),
        )
        conn.execute(
            "UPDATE knowledge_objects SET fetched_at=? WHERE id='ko-2'",
            ("2026-10-20T06:59:59+07:00",),
        )
    assert [r["item"].id for r in access.load_intelligence_inputs(DAY)["candidates"]] == ["ko-1"]
    assert day_start(DAY).hour == 0


def test_bootstrap_and_registry_initializer_share_existing_chain(environment, monkeypatch):
    store, _, provider, _ = environment
    initializer = MagicMock(sqlite_store=store)
    service = create_intelligence_service(initializer, provider)
    assert isinstance(service, InsightGenerator) and service._provider is provider
    registry = MagicMock()
    registry.get_component.side_effect = {"repository": initializer, "llm_chain": provider}.get
    monkeypatch.setattr(application, "_registry", registry)
    assert application._init_intelligence()._provider is provider
    provider.structured_chat.assert_not_called()


def test_sql_failure_after_delete_rolls_back_the_complete_replacement(environment):
    import sqlite3

    store, access, _, generator = environment
    generator.generate_insights(DAY)
    before = access.read_insight_report(DAY)
    with store._conn_manager.get_connection() as conn:
        conn.execute(
            "CREATE TRIGGER reject_insight BEFORE INSERT ON insights "
            "BEGIN SELECT RAISE(ABORT, 'test failure'); END"
        )
    with pytest.raises(sqlite3.IntegrityError, match="test failure"):
        generator.generate_insights(DAY)
    assert access.read_insight_report(DAY) == before


def test_thirty_candidate_limit_and_no_provider_for_truly_empty_report(environment):
    from app.config.importance import ImportanceConfig
    from app.services.importance.scorer import ImportanceScorer
    from app.services.trend.models import TrendRun
    from tests.fakes.analysis import make_analysis, make_knowledge

    store, access, provider, generator = environment
    for i in range(3, 35):
        analysis = make_analysis(i, at=NOW)
        obj = make_knowledge(analysis).model_copy(update={"fetched_at": day_start(DAY)})
        store.save_objects([obj])
        access.save_content_analysis(analysis)
    ImportanceScorer(access, None, ImportanceConfig(llm_top_n=0), clock=lambda: NOW).score_batch(
        [f"ko-{i}" for i in range(3, 35)]
    )
    data = access.load_intelligence_inputs(DAY)
    assert data["total_items"] == 35 and len(data["candidates"]) == 30
    with store._conn_manager.get_connection() as conn:
        conn.execute("UPDATE knowledge_objects SET fetched_at='2026-10-18T00:00:00+00:00'")
    empty_run = TrendRun(
        week="2026-W42",
        baseline_week="2026-W41",
        computed_at=NOW,
        current_items=0,
        baseline_items=0,
        snapshot_count=0,
        min_count=1,
    )
    access.save_trend_snapshots([], run=empty_run)
    assert generator.generate_insights(DAY) == []
    provider.structured_chat.assert_not_called()
    assert access.read_insight_report(DAY)[0].candidate_count == 0


def test_pattern_requires_its_persisted_evidence(environment):
    from app.services.analysis.models import DiscoveredPattern

    _, access, provider, generator = environment
    pattern = DiscoveredPattern(
        pattern_id="pattern-1",
        pattern_type="recurring",
        topic="rag",
        time_window_days=14,
        description="Observed recurrence",
        confidence=0.8,
        evidence_ids=["ko-0", "ko-1"],
        first_detected=NOW,
        metrics={},
    )
    access.save_discovered_patterns([pattern], NOW)
    provider.structured_chat.return_value = InsightBatch(
        insights=[draft(insight_type="pattern", signal_ids=["pattern-1"])]
    )
    assert generator.generate_insights(DAY)[0].insight_type == "pattern"
