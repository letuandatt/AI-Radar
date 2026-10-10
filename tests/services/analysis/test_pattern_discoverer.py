"""Pattern rules, evidence, structured descriptions, errors and performance."""

from datetime import timedelta
from html import unescape
from time import perf_counter
from unittest.mock import MagicMock

import pytest

from app.integrations.llm.provider import LLMProvider
from app.prompts.loader import PromptLoader
from app.services.analysis.models import PatternDescriptions
from app.services.analysis.pattern_discoverer import PatternDiscoverer
from app.services.repository.access_service import RepositoryAccessService
from tests.fakes.analysis import NOW
from tests.fakes.patterns import describe, hundred_items, observed, thousand_items


def build(items, batch_size=10):
    access = MagicMock(spec=RepositoryAccessService)
    access.list_pattern_items.return_value = items
    access.save_discovered_patterns.side_effect = lambda patterns, observed_at: patterns
    llm = MagicMock(spec=LLMProvider)
    llm.structured_chat.side_effect = describe
    service = PatternDiscoverer(access, llm, PromptLoader(), batch_size, clock=lambda: NOW)
    return service, access, llm


def test_hundred_objects_across_sixty_days_find_three_patterns():
    items = hundred_items()
    assert len(items) == 100
    service, access, llm = build(items)
    patterns = service.discover_patterns()
    by_type = {p.pattern_type: p for p in patterns}
    assert len(patterns) == 3
    assert by_type["emerging"].topic == "theme:new"
    assert len(by_type["emerging"].evidence_ids) == 10
    assert by_type["recurring"].metrics["weekly_counts_newest_first"] == [5, 5, 5, 5]
    assert by_type["recurring"].metrics["cv"] == 0
    assert by_type["declining"].metrics["decline_ratio"] == pytest.approx(2 / 3)
    assert len(by_type["declining"].evidence_ids) == 40
    assert all(p.confidence == pytest.approx(0.8) and p.description.strip() for p in patterns)
    assert all(set(p.evidence_ids) <= {i.knowledge_id for i in items} for p in patterns)
    access.list_pattern_items.assert_called_once_with(NOW - timedelta(days=60), NOW)
    access.save_discovered_patterns.assert_called_once_with(patterns, observed_at=NOW)
    assert llm.structured_chat.call_count == 1


@pytest.mark.parametrize(("current_count", "declines"), [(10, False), (9, True), (0, True)])
def test_decline_is_strictly_more_than_half(current_count, declines):
    items = [observed(i, 40) for i in range(20)]
    items += [observed(i + 20, 15) for i in range(current_count)]
    service, _, _ = build(items)
    assert any(p.pattern_type == "declining" for p in service.discover_patterns()) is declines


@pytest.mark.parametrize(
    ("counts", "recurs"), [([13, 7, 13, 7], False), ([12, 8, 12, 8], True), ([5, 0, 5, 0], False)]
)
def test_cv_threshold_and_missing_weeks(counts, recurs):
    items = []
    for week, count in enumerate(counts):
        items += [observed(len(items) + i, 1 + week * 7) for i in range(count)]
    service, _, _ = build(items)
    assert any(p.pattern_type == "recurring" for p in service.discover_patterns()) is recurs


def test_emerging_windows_do_not_overlap():
    # Exactly 7 days belongs to the baseline; exactly 37 days is outside it.
    for age, expected in [(7, False), (37, True)]:
        service, _, _ = build([observed(0, 1), observed(1, age)])
        assert any(p.pattern_type == "emerging" for p in service.discover_patterns()) is expected


def test_week_boundaries_and_incomplete_week():
    items = [observed(i, age) for i, age in enumerate([0, 7, 14, 21, 28, 29])]
    service, _, _ = build(items)
    recurring = next(p for p in service.discover_patterns() if p.pattern_type == "recurring")
    assert recurring.metrics["weekly_counts_newest_first"] == [1, 1, 1, 1]
    assert recurring.metrics["current_count"] == 6
    assert recurring.metrics["weekly_window_days"] == 28
    assert recurring.metrics["weekly_excluded_count"] == 2
    assert recurring.evidence_ids == ["ko-0", "ko-1", "ko-2", "ko-3"]


@pytest.mark.parametrize(
    ("days", "weekly_days", "excluded"), [(28, 28, 0), (30, 28, 2), (35, 35, 0)]
)
def test_weekly_metrics_explain_full_window_counts_to_llm(days, weekly_days, excluded):
    service, _, llm = build([observed(i, i) for i in range(days)])
    recurring = next(p for p in service.discover_patterns(days) if p.pattern_type == "recurring")
    metrics = recurring.metrics
    assert metrics["current_count"] == days
    assert metrics["weekly_window_days"] == weekly_days
    assert metrics["weekly_excluded_count"] == excluded
    assert sum(metrics["weekly_counts_newest_first"]) + excluded == days
    prompt = unescape(llm.structured_chat.call_args.args[0])
    assert f'"weekly_window_days": {weekly_days}' in prompt
    assert f'"weekly_excluded_count": {excluded}' in prompt


def test_custom_window_and_multiple_labels():
    items = [observed(i, 40) for i in range(20)]
    items += [observed(i + 20, age) for i, age in enumerate([1, 8, 15, 22])]
    service, _, _ = build(items)
    assert {p.pattern_type for p in service.discover_patterns()} == {"recurring", "declining"}
    _, access, _ = build([])
    short = PatternDiscoverer(access, MagicMock(), PromptLoader(), clock=lambda: NOW)
    assert short.discover_patterns(7) == []
    access.list_pattern_items.assert_called_with(NOW - timedelta(days=14), NOW)


def test_empty_data_and_unknown_history():
    service, access, llm = build([])
    assert service.discover_patterns() == []
    llm.structured_chat.assert_not_called()
    access.save_discovered_patterns.assert_not_called()
    access.get_pattern_history.return_value = []
    assert service.get_pattern_history("unknown") == []
    with pytest.raises(ValueError):
        service.get_pattern_history(" ")


def test_many_topics_are_not_limited_by_cross_source_top_twenty():
    service, _, llm = build([observed(i, topic=f"topic-{i}") for i in range(25)], batch_size=10)
    assert len(service.discover_patterns()) == 25
    assert llm.structured_chat.call_count == 3


@pytest.mark.parametrize("mode", ["missing", "duplicate", "unknown", "blank", "provider_error"])
def test_bad_description_batches_do_not_write_partial_run(mode):
    service, access, llm = build(hundred_items(), batch_size=2)
    calls = 0

    def respond(prompt, schema):
        nonlocal calls
        calls += 1
        response = describe(prompt, schema)
        if calls == 1:
            return response
        rows = response.model_dump()["descriptions"]
        if mode == "missing":
            rows = []
        elif mode == "duplicate":
            rows += rows
        elif mode == "unknown":
            rows[0]["pattern_id"] = "wrong"
        elif mode == "blank":
            rows[0]["description"] = "   "
        else:
            raise RuntimeError("provider unavailable")
        return PatternDescriptions(descriptions=rows)

    llm.structured_chat.side_effect = respond
    with pytest.raises((ValueError, RuntimeError)):
        service.discover_patterns()
    access.save_discovered_patterns.assert_not_called()


@pytest.mark.parametrize("days", [0, 6, True, 7.5, 10**10])
def test_invalid_window_is_rejected(days):
    service, access, _ = build([])
    with pytest.raises(ValueError):
        service.discover_patterns(days)
    access.list_pattern_items.assert_not_called()


@pytest.mark.performance
def test_thousand_objects_under_ten_seconds():
    items = thousand_items()
    service, access, llm = build(items)
    start = perf_counter()
    results = service.discover_patterns()
    elapsed = perf_counter() - start
    assert results and elapsed < 10
    access.list_pattern_items.assert_called_once()
    print(
        f"1000 items: {elapsed:.4f}s; patterns={len(results)}; "
        f"LLM batches={llm.structured_chat.call_count}"
    )
