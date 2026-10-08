"""Cross-source grouping, coverage, validation and performance contracts."""

from time import perf_counter
from unittest.mock import MagicMock

import pytest

from app.integrations.llm.provider import LLMProvider
from app.services.analysis.cross_source_analyzer import CrossSourceAnalyzer
from app.services.repository.access_service import RepositoryAccessService
from tests.fakes.analysis import NOW, make_analysis, twenty_analyses


def build_analyzer(items, max_groups=20):
    access = MagicMock(spec=RepositoryAccessService)
    access.list_items_in_window.return_value = items
    provider = MagicMock(spec=LLMProvider)
    return CrossSourceAnalyzer(access, provider, max_groups), access, provider


def test_twenty_items_from_three_sources():
    analyzer, access, provider = build_analyzer(twenty_analyses())
    groups = analyzer.find_groups()
    assert [group.topic for group in groups] == ["companies:openai", "theme:rag"]
    for group in groups:
        assert set(group.knowledge_ids) == {f"ko-{i}" for i in range(14)}
        assert group.sources == ["rss:a", "rss:b"]
        assert group.source_count == 2
        assert group.coverage_score == pytest.approx(2 / 3)
        assert group.first_seen == twenty_analyses()[13].analyzed_at
        assert group.last_seen == NOW
    access.list_items_in_window.assert_called_once_with(7)
    access.save_cross_source_groups.assert_called_once_with(groups, time_window_days=7)
    assert provider.mock_calls == []


@pytest.mark.parametrize(
    ("topic", "count", "sources", "score"),
    [("RAG", 14, 2, 2 / 3), ("vision", 6, 1, 1 / 3), ("unknown", 0, 0, 0)],
)
def test_coverage_includes_single_source_and_missing_topics(topic, count, sources, score):
    analyzer, access, _ = build_analyzer(twenty_analyses())
    result = analyzer.find_coverage(topic)
    assert result.article_count == count
    assert result.source_count == sources
    assert result.total_sources == 3
    assert result.coverage_score == pytest.approx(score)
    assert (result.first_seen is None) == (count == 0)
    assert (result.last_seen is None) == (count == 0)
    access.save_cross_source_groups.assert_not_called()


def test_normalization_namespaces_and_non_transitive_membership():
    items = [
        make_analysis(0, "a", [" A ", "a", "OpenAI"]),
        make_analysis(1, "b", ["a", "B"], {"companies": ["OpenAI"]}),
        make_analysis(2, "c", ["b"], {"companies": [" openai "]}),
    ]
    analyzer, _, _ = build_analyzer(items)
    groups = {group.topic: group for group in analyzer.find_groups()}
    assert set(groups) == {"theme:a", "theme:b", "companies:openai"}
    assert groups["theme:a"].knowledge_ids == ["ko-0", "ko-1"]
    assert groups["theme:b"].knowledge_ids == ["ko-1", "ko-2"]
    assert analyzer.find_coverage(" COMPANIES: OpenAI ").source_count == 2
    assert analyzer.find_coverage("openai").source_count == 1


def test_top_n_limits_return_only_and_sort_is_stable():
    items = [make_analysis(i, str(i % 3), [f"topic-{i // 3:02d}"]) for i in range(75)]
    analyzer, access, _ = build_analyzer(items)
    groups = analyzer.find_groups()
    assert len(groups) == 20
    assert len(access.save_cross_source_groups.call_args.args[0]) == 25
    assert groups[0].topic == "theme:topic-00"
    assert all(group.coverage_score == 1.0 for group in groups)
    assert analyzer.find_coverage("topic-24").article_count == 3
    access.list_items_in_window.return_value = list(reversed(items))
    assert analyzer.find_groups() == groups
    limited, _, _ = build_analyzer(items, max_groups=1)
    assert limited.find_groups() == groups[:1]
    assert limited.find_groups(30)[0].group_id != groups[0].group_id


def test_ranking_uses_coverage_then_article_count():
    items = [make_analysis(i, str(i), ["wide"]) for i in range(3)]
    items += [make_analysis(i + 3, str(i % 2), ["many"]) for i in range(6)]
    items += [make_analysis(i + 9, str(i), ["few"]) for i in range(2)]
    analyzer, _, _ = build_analyzer(items)
    assert [g.topic for g in analyzer.find_groups()] == ["theme:wide", "theme:many", "theme:few"]


def test_source_identity_uses_type_and_name_without_separator_collisions():
    items = [
        make_analysis(0, "b:c", source_type="a"),
        make_analysis(1, "c", source_type="a:b"),
        make_analysis(2, "b:c", source_type="github"),
    ]
    analyzer, _, _ = build_analyzer(items)
    group = analyzer.find_groups()[0]
    assert group.source_count == 3
    assert len(set(group.sources)) == 3
    assert group.coverage_score == 1.0


def test_empty_data_clears_snapshot_and_has_zero_coverage():
    analyzer, access, _ = build_analyzer([])
    assert analyzer.find_groups() == []
    access.save_cross_source_groups.assert_called_once_with([], time_window_days=7)
    coverage = analyzer.find_coverage("RAG")
    assert coverage.total_sources == 0
    assert coverage.coverage_score == 0.0


@pytest.mark.parametrize("value", [0, -1, True, 1.5])
def test_invalid_window_and_limit(value):
    analyzer, access, _ = build_analyzer([])
    with pytest.raises(ValueError):
        analyzer.find_groups(value)
    with pytest.raises(ValueError):
        analyzer.find_coverage("rag", value)
    with pytest.raises(ValueError):
        build_analyzer([], value)
    access.list_items_in_window.assert_not_called()


@pytest.mark.parametrize("topic", ["", "  ", "theme: ", "companies:"])
def test_empty_topic_is_rejected(topic):
    analyzer, access, _ = build_analyzer([])
    with pytest.raises(ValueError):
        analyzer.find_coverage(topic)
    access.list_items_in_window.assert_not_called()


def test_storage_errors_are_not_reported_as_success():
    analyzer, access, _ = build_analyzer(twenty_analyses())
    access.save_cross_source_groups.side_effect = RuntimeError("disk unavailable")
    with pytest.raises(RuntimeError, match="disk unavailable"):
        analyzer.find_groups()


@pytest.mark.performance
def test_one_thousand_objects_under_five_seconds():
    items = [make_analysis(i, str(i % 3), [f"topic-{i % 20}"]) for i in range(1000)]
    analyzer, _, provider = build_analyzer(items)
    start = perf_counter()
    groups = analyzer.find_groups()
    elapsed = perf_counter() - start
    assert len(groups) == 20
    assert sum(len(group.knowledge_ids) for group in groups) == 1000
    assert elapsed < 5.0
    assert provider.mock_calls == []
    print(f"Grouping 1000 items: {elapsed:.4f}s")
