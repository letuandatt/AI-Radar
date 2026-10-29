"""Real SQLite generation/composition/refinement with bounded mock LLM output."""

import html
import json
from datetime import timedelta
from time import perf_counter

import pytest

from app.services.intelligence.context import sync_section
from app.services.intelligence.models import (
    ContentBlock,
    IntelligenceDocument,
    IntelligenceMetadata,
    RefinementEdit,
    RefinementOutput,
)
from app.services.intelligence.refiner import IntelligenceRefiner
from tests.services.intelligence.conftest import NOW
from tests.services.intelligence.test_composer import composer


def payload(prompt):
    return json.loads(
        html.unescape(prompt.split("<untrusted_data>\n")[1].split("\n</untrusted_data>")[0])
    )


def echo(prompt, schema):
    data = payload(prompt)
    return schema(
        edits=[
            {
                "block_id": block["block_id"],
                "text": block["text"],
                "evidence_ids": block["evidence_ids"],
            }
            for block in data["blocks"]
        ],
        issues=[],
    )


def rebuild(document):
    document.sections = [sync_section(section) for section in document.sections]
    document.metadata = IntelligenceMetadata.from_sections(document.sections)
    return IntelligenceDocument.model_validate(document.model_dump())


@pytest.fixture
def prepared(environment):
    document = composer(environment).compose("2026-10-20")
    _, access, provider, _ = environment
    provider.reset_mock()
    provider.structured_chat.side_effect = echo
    refiner = IntelligenceRefiner(access, provider, clock=lambda: NOW + timedelta(seconds=1))
    return document, refiner, provider


def test_end_to_end_preserves_facts_sources_and_input_with_mock_performance(prepared):
    document, refiner, provider = prepared
    before = document.model_dump()
    start = perf_counter()
    result = refiner.refine(document)
    assert perf_counter() - start < 30
    assert document.model_dump() == before
    assert result is not document and result.sections[0] is not document.sections[0]
    assert len(result.to_markdown().split()) < 2000
    assert result.refined_at == NOW + timedelta(seconds=1)
    assert result.document_id == document.document_id
    assert result.generated_at == document.generated_at
    assert result.sections[1] == document.sections[1]  # Fixed numerical trend table.
    assert result.metadata == document.metadata
    provider.structured_chat.assert_called_once()
    assert IntelligenceDocument.model_validate_json(result.model_dump_json()) == result


def test_dedup_equivalent_insights_and_citations_but_preserve_other_claims(prepared):
    document, refiner, _ = prepared
    section = document.sections[2]
    original = section.insights[0]
    duplicate = original.model_copy(update={"insight_id": "duplicate"})
    different = original.model_copy(
        update={"insight_id": "different", "description": "A different finding."}
    )
    section.insights.extend([duplicate, different])
    block = section.blocks[0]
    section.blocks.extend(
        [
            block.model_copy(update={"block_id": "duplicate-block", "insight_id": "duplicate"}),
            block.model_copy(
                update={
                    "block_id": "different-block",
                    "insight_id": "different",
                    "text": different.description,
                }
            ),
        ]
    )
    document = rebuild(document)
    section = document.sections[2]
    section.citations.extend(section.citations.copy())
    before = document.model_dump()
    result = refiner.refine(document)
    assert len(result.sections[2].insights) == 2
    assert len(result.sections[2].blocks) == 2
    assert result.metadata.total_insights == 2
    assert result.metadata.total_citations == 3
    assert document.model_dump() == before


def test_same_sources_with_different_prose_are_not_deduplicated(prepared):
    document, refiner, _ = prepared
    section = document.sections[0]
    assert len(section.blocks) == 3
    result = refiner.refine(document)
    assert len(result.sections[0].blocks) == 3


def test_duplicate_prose_is_removed_within_section(prepared):
    document, refiner, _ = prepared
    section = document.sections[0]
    section.blocks.append(section.blocks[0].model_copy(update={"block_id": "duplicate-prose"}))
    document = rebuild(document)
    assert len(refiner.refine(document).sections[0].blocks) == 3


@pytest.mark.parametrize(
    "mode", ["missing", "duplicate", "unknown", "evidence", "numbers", "issues"]
)
def test_invalid_llm_edits_fail_without_mutating_input(prepared, mode):
    document, refiner, provider = prepared
    before = document.model_dump()

    def invalid(prompt, schema):
        response = echo(prompt, schema).model_dump()
        if mode == "missing":
            response["edits"].pop()
        elif mode == "duplicate":
            response["edits"][-1] = response["edits"][0]
        elif mode == "unknown":
            response["edits"][0]["block_id"] = "invented"
        elif mode == "evidence":
            response["edits"][0]["evidence_ids"] = ["invented"]
        elif mode == "numbers":
            response["edits"][0]["text"] = "Unsupported numeric claim 999."
        else:
            response["issues"] = ["The supplied claims contradict each other."]
        return schema(**response)

    provider.structured_chat.side_effect = invalid
    with pytest.raises(ValueError):
        refiner.refine(document)
    assert document.model_dump() == before
    assert provider.structured_chat.call_count == 1


def test_provider_construct_is_revalidated(prepared):
    document, refiner, provider = prepared
    provider.structured_chat.side_effect = None
    provider.structured_chat.return_value = RefinementOutput.model_construct(
        edits=[RefinementEdit.model_construct(block_id="bad", text="", evidence_ids=[])]
    )
    with pytest.raises(ValueError):
        refiner.refine(document)


@pytest.mark.parametrize("mode", ["legacy", "content", "citation", "block_id"])
def test_invalid_input_fails_before_provider(prepared, mode):
    document, refiner, provider = prepared
    if mode == "legacy":
        document.sections[0].blocks = []
    elif mode == "content":
        document.sections[0].content += " Forged prose."
    elif mode == "citation":
        document.sections[0].citations = []
        document.metadata = IntelligenceMetadata.from_sections(document.sections)
    else:
        document.sections[0].blocks[1].block_id = document.sections[0].blocks[0].block_id
    with pytest.raises(ValueError):
        refiner.refine(document)
    provider.structured_chat.assert_not_called()


@pytest.mark.parametrize("mode", ["deleted", "changed"])
def test_source_integrity_checked_before_llm(environment, prepared, mode):
    store, _, _, _ = environment
    document, refiner, provider = prepared
    if mode == "deleted":
        store.delete_by_id("ko-0")
    else:
        store.update_by_id("ko-0", {"title": "New title"})
    with pytest.raises((ValueError, LookupError)):
        refiner.refine(document)
    provider.structured_chat.assert_not_called()


def test_source_drift_during_llm_is_detected(environment, prepared):
    document, refiner, provider = prepared
    before = document.model_dump()

    def change(prompt, schema):
        environment[0].update_by_id("ko-0", {"source_url": "https://example.com/changed"})
        return echo(prompt, schema)

    provider.structured_chat.side_effect = change
    with pytest.raises(ValueError, match="source changed"):
        refiner.refine(document)
    assert document.model_dump() == before


def test_length_retry_shortens_prose_without_cutting_links(prepared):
    document, refiner, provider = prepared
    document.sections[3].blocks[0].text = "Repeated wording. " * 1500
    document = rebuild(document)
    before = document.model_dump()

    def shorten(prompt, schema):
        response = echo(prompt, schema)
        if "length_feedback" in payload(prompt):
            response.edits[-3].text = "Repeated wording."
        return response

    provider.structured_chat.side_effect = shorten
    result = refiner.refine(document)
    assert provider.structured_chat.call_count == 2
    assert len(result.to_markdown().split()) < 2000
    assert result.sections[1].content == document.sections[1].content
    assert result.metadata == document.metadata
    assert document.model_dump() == before
    assert "](https://example.com/ko-0)" in result.to_markdown()


@pytest.mark.parametrize("words", [1999, 2000])
def test_exact_final_markdown_word_boundary(prepared, words):
    document, refiner, provider = prepared
    block = document.sections[3].blocks[0]
    block.text = "word"
    document = rebuild(document)
    baseline = len(document.to_markdown().split())
    document.sections[3].blocks[0].text = " ".join(["word"] * (words - baseline + 1))
    document = rebuild(document)
    assert len(document.to_markdown().split()) == words
    if words == 1999:
        assert len(refiner.refine(document).to_markdown().split()) == 1999
        assert provider.structured_chat.call_count == 1
    else:
        with pytest.raises(ValueError, match="still exceeds"):
            refiner.refine(document)
        assert provider.structured_chat.call_count == 2


def test_fixed_overhead_cannot_be_silently_dropped(prepared):
    document, refiner, provider = prepared
    document.sections[1].blocks[0].text = ("Fixed observations. " * 1500).strip()
    document = rebuild(document)
    with pytest.raises(ValueError, match="Fixed facts"):
        refiner.refine(document)
    provider.structured_chat.assert_not_called()


def test_batch_order_failure_and_empty_batch(prepared):
    document, refiner, provider = prepared
    other = document.model_copy(deep=True, update={"document_id": "second"})
    results = refiner.refine_batch([document, other])
    assert [row.document_id for row in results] == [document.document_id, "second"]
    assert refiner.refine_batch([]) == []
    provider.structured_chat.side_effect = RuntimeError("provider offline")
    with pytest.raises(RuntimeError, match="provider offline"):
        refiner.refine_batch([document, other])
    assert document.refined_at is None and other.refined_at is None


def test_notices_need_no_provider_or_fake_citations(prepared):
    document, refiner, provider = prepared
    for index, section in enumerate(document.sections):
        section.blocks = [ContentBlock(block_id=str(index), kind="notice", text="No observations.")]
        section.insights = []
        section.citations = []
        section.trend_ids = []
    document = rebuild(document)
    result = refiner.refine(document)
    provider.structured_chat.assert_not_called()
    assert result.metadata.total_insights == result.metadata.total_citations == 0
    assert result.refined_at is not None
