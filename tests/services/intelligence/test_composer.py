"""Four-section composition and source-safe Markdown using real SQLite."""

from unittest.mock import patch

import pytest

from app.services.intelligence.composer import IntelligenceComposer
from app.services.intelligence.models import ExecutiveSummary, InsightBatch, SummarySentence
from tests.services.intelligence.conftest import DAY, NOW, draft


def composer(environment):
    _, access, provider, generator = environment
    generator.generate_insights(DAY)
    provider.structured_chat.return_value = ExecutiveSummary(
        sentences=[
            SummarySentence(text=f"Supported finding {i}.", evidence_ids=["ko-0", "ko-1"])
            for i in range(3)
        ]
    )
    return IntelligenceComposer(access, provider, clock=lambda: NOW)


def test_four_sections_citations_unique_metadata_and_markdown(environment):
    service = composer(environment)
    document = service.compose(DAY)
    assert [row.section_type for row in document.sections] == [
        "executive_summary",
        "top_trends",
        "key_insights",
        "notable_items",
    ]
    assert all(section.content and section.citations for section in document.sections)
    assert document.metadata.total_insights == 1
    assert document.metadata.total_trends == 1  # Repeated in growing and topic tables.
    assert document.metadata.total_citations == 3
    assert document.metadata.confidence_avg == 0.8
    markdown = document.to_markdown()
    assert markdown.startswith(f"# Daily intelligence — {DAY}\n")
    assert "| Rank |" in markdown and "https://example.com/ko-0" in markdown
    for section in document.sections:
        assert len(section.citations) == len({row.knowledge_id for row in section.citations})


def test_top_five_insights_and_top_ten_notable(environment):
    _, _, provider, _ = environment
    provider.structured_chat.return_value = InsightBatch(
        insights=[draft(title=f"Finding {i}", confidence=i / 10) for i in range(10)]
    )
    result = composer(environment).compose(DAY)
    assert len(result.sections[2].insights) == 5
    assert [row.confidence for row in result.sections[2].insights] == [0.9, 0.8, 0.7, 0.6, 0.5]
    assert result.metadata.confidence_avg == pytest.approx(0.7)
    assert len(result.sections[3].citations) == 3


def test_missing_insight_run_is_not_empty_success(environment):
    _, access, provider, _ = environment
    with pytest.raises(LookupError, match="No insight run"):
        IntelligenceComposer(access, provider, clock=lambda: NOW).compose(DAY)
    provider.structured_chat.assert_not_called()


def test_successful_empty_insights_still_composes_notable_items(environment):
    _, _, provider, _ = environment
    provider.structured_chat.return_value = InsightBatch(insights=[])
    result = composer(environment).compose(DAY)
    assert result.metadata.total_insights == 0
    assert result.metadata.confidence_avg == 0
    assert result.sections[2].citations == []
    assert result.sections[0].content and result.sections[3].citations


@pytest.mark.parametrize("count", [0, 2, 6])
def test_summary_sentence_count_revalidated(environment, count):
    service = composer(environment)
    provider = environment[2]
    sentence = SummarySentence(text="Finding.", evidence_ids=["ko-0"])
    provider.structured_chat.return_value = ExecutiveSummary.model_construct(
        sentences=[sentence] * count
    )
    with pytest.raises(ValueError):
        service.compose(DAY)


def test_unknown_summary_evidence_rejected(environment):
    service = composer(environment)
    environment[2].structured_chat.return_value = ExecutiveSummary(
        sentences=[SummarySentence(text="Finding.", evidence_ids=["invented"]) for _ in range(3)]
    )
    with pytest.raises(ValueError, match="unknown evidence"):
        service.compose(DAY)


def test_saved_citation_drift_requires_regeneration(environment):
    service = composer(environment)
    store, _, provider, _ = environment
    store.update_by_id("ko-0", {"title": "Changed title"})
    provider.reset_mock()
    with pytest.raises(ValueError, match="source changed"):
        service.compose(DAY)
    provider.structured_chat.assert_not_called()


def test_report_replacement_during_composition_is_detected(environment):
    service = composer(environment)
    _, access, _, _ = environment
    saved = access.read_insight_report(DAY)
    with patch.object(access, "read_insight_report", side_effect=[saved, (None, [])]):
        with pytest.raises(RuntimeError, match="changed during composition"):
            service.compose(DAY)


def test_untrusted_text_cannot_create_markdown_links(environment):
    service = composer(environment)
    environment[2].structured_chat.return_value = ExecutiveSummary(
        sentences=[
            SummarySentence(
                text="[Fake](https://evil.test) <script>bad</script>.", evidence_ids=["ko-0"]
            )
            for _ in range(3)
        ]
    )
    content = service.compose(DAY).sections[0].content
    assert "[Fake](https://evil.test)" not in content
    assert "<script>" not in content
    assert "](https://example.com/ko-0)" in content


def test_blocks_round_trip_and_render_match_sections(environment):
    from app.services.intelligence.context import render_section
    from app.services.intelligence.models import IntelligenceDocument

    document = composer(environment).compose(DAY)
    restored = IntelligenceDocument.model_validate_json(document.model_dump_json())
    assert restored == document
    ids = []
    for section in restored.sections:
        assert section.blocks
        assert render_section(section) == section.content
        ids.extend(block.block_id for block in section.blocks)
        for block in section.blocks:
            if block.kind != "notice":
                assert block.evidence_ids
    assert len(ids) == len(set(ids))
    assert restored.sections[1].blocks[0].kind == "fixed"
