"""Conservative deduplication and bounded LLM editing over explicit cited blocks."""

import json
import re
from collections.abc import Callable
from datetime import datetime, timezone

from app.core.logger import get_logger
from app.integrations.llm.provider import LLMProvider
from app.prompts.builder import PromptBuilder
from app.prompts.loader import PromptLoader
from app.services.intelligence.context import resolve_citation, sync_section
from app.services.intelligence.models import (
    Citation,
    Insight,
    IntelligenceDocument,
    IntelligenceMetadata,
    RefinementOutput,
)
from app.services.repository.access_service import RepositoryAccessService

logger = get_logger(__name__)
MAX_WORDS = 1999


def _normalized(value: str) -> str:
    return " ".join(value.split()).casefold()


def _insight_key(row: Insight) -> tuple:
    # Identical evidence alone never proves identical findings.
    return (
        row.insight_type,
        _normalized(row.title),
        _normalized(row.description),
        tuple(sorted(row.evidence_ids)),
        tuple(sorted(row.signal_ids)),
    )


def _numbers(value: str) -> list[str]:
    return re.findall(r"[+-]?\d+(?:[.,]\d+)*%?", value)


class IntelligenceRefiner:
    """Read-only sync API; async callers must offload the whole call with to_thread.

    Makes at most two sequential LLM calls per document (second for length only).
    Input objects and persisted insights are never mutated. Deduplication is
    conservative: equivalent normalized claims and evidence, not semantic guesses.
    Citation/number checks are structural guards, not proof of semantic truth.
    """

    def __init__(
        self,
        access_service: RepositoryAccessService,
        llm_provider: LLMProvider,
        *,
        prompt_loader: PromptLoader | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._access = access_service
        self._provider = llm_provider
        self._prompts = prompt_loader or PromptLoader()
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def refine(self, document: IntelligenceDocument) -> IntelligenceDocument:
        """Return a validated, cited document below 2000 words or raise without changes."""
        result = IntelligenceDocument.model_validate(document.model_dump()).model_copy(deep=True)
        result.refined_at = None
        logger.info("Intelligence refinement START: date=%s", result.date)
        self._validate_input(result)
        self._check_sources(result)
        self._deduplicate(result)
        blocks = {
            block.block_id: block
            for section in result.sections
            for block in section.blocks
            if block.kind == "prose"
        }
        # Compute rendered fixed overhead, including headings, facts and links.
        skeleton = result.model_copy(deep=True)
        for section in skeleton.sections:
            for block in section.blocks:
                if block.kind == "prose":
                    block.text = ""
            section.content = sync_section(section).content
        available = MAX_WORDS - len(skeleton.to_markdown().split())
        if available < len(blocks):
            raise ValueError(
                "Fixed facts and citations exceed the word budget; cannot safely shorten"
            )
        if blocks:
            payload = {
                "report_date": result.date,
                "prose_word_budget": available,
                "blocks": [block.model_dump(mode="json") for block in blocks.values()],
                "fixed_context": [
                    block.model_dump(mode="json")
                    for section in result.sections
                    for block in section.blocks
                    if block.kind != "prose"
                ],
            }
            for attempt in range(2):
                prompt = (
                    PromptBuilder(self._prompts.load("intelligence/refinement"))
                    .with_untrusted_data(json.dumps(payload, ensure_ascii=False, allow_nan=False))
                    .build()
                )
                logger.info(
                    "Intelligence refinement LLM: attempt=%d, blocks=%d", attempt + 1, len(blocks)
                )
                output = self._provider.structured_chat(prompt, RefinementOutput)
                edits = RefinementOutput.model_validate(output.model_dump())
                if edits.issues:
                    raise ValueError("Unresolved refinement issues: " + "; ".join(edits.issues))
                if (
                    len(edits.edits) != len(blocks)
                    or {row.block_id for row in edits.edits} != blocks.keys()
                ):
                    raise ValueError("Refinement must return every editable block exactly once")
                for edit in edits.edits:
                    original = blocks[edit.block_id]
                    if edit.evidence_ids != original.evidence_ids:
                        raise ValueError("Refinement cannot change block evidence")
                    if _numbers(edit.text) != _numbers(original.text):
                        raise ValueError("Refinement cannot change numeric facts")
                for edit in edits.edits:
                    for section in result.sections:
                        for block in section.blocks:
                            if block.block_id == edit.block_id:
                                block.text = edit.text
                result.sections = [sync_section(section) for section in result.sections]
                if len(result.to_markdown().split()) <= MAX_WORDS:
                    break
                payload["length_feedback"] = (
                    "Previous output exceeded the final Markdown limit. Shorten wording, "
                    "preserve all facts, qualifiers and evidence, and return every block."
                )
            else:
                raise ValueError(
                    "Refined document still exceeds 1999 words; input remains unchanged"
                )
        result.metadata = IntelligenceMetadata.from_sections(result.sections)
        self._check_sources(result)
        result.refined_at = self._clock()
        result = IntelligenceDocument.model_validate(result.model_dump())
        logger.info("Intelligence refinement DONE: words=%d", len(result.to_markdown().split()))
        return result

    def refine_batch(self, documents: list[IntelligenceDocument]) -> list[IntelligenceDocument]:
        """Refine sequentially in input order; any failure raises with no persisted writes.

        Earlier calls may consume provider budget. No partial result list is returned.
        """
        return [self.refine(document) for document in documents]

    def _validate_input(self, document: IntelligenceDocument) -> None:
        block_ids: list[str] = []
        for section in document.sections:
            rebuilt = sync_section(section)
            if rebuilt.content != section.content:
                raise ValueError("Section content does not match blocks; run composition again")
            if {row.insight_id for row in rebuilt.insights} != {
                row.insight_id for row in section.insights
            }:
                raise ValueError("Section contains insights without content blocks")
            if set(rebuilt.trend_ids) != set(section.trend_ids):
                raise ValueError("Section trend IDs do not match blocks")
            if {row.knowledge_id for row in rebuilt.citations} != {
                row.knowledge_id for row in section.citations
            }:
                raise ValueError("Section citations do not match blocks")
            block_ids.extend(block.block_id for block in section.blocks)
        if len(block_ids) != len(set(block_ids)):
            raise ValueError("Content block IDs must be globally unique")

    def _check_sources(self, document: IntelligenceDocument) -> None:
        citations: dict[str, Citation] = {}
        for section in document.sections:
            for row in [
                *section.citations,
                *[c for insight in section.insights for c in insight.citations],
            ]:
                if row.knowledge_id in citations and citations[row.knowledge_id] != row:
                    raise ValueError("Conflicting citation records")
                citations[row.knowledge_id] = row
        for identity, citation in citations.items():
            if resolve_citation(self._access, identity) != citation:
                raise ValueError("Citation source changed; regenerate and compose again")

    @staticmethod
    def _deduplicate(document: IntelligenceDocument) -> None:
        for section in document.sections:
            by_id: dict[str, Insight] = {}
            canonical: dict[tuple, Insight] = {}
            replacements = {}
            for row in section.insights:
                if row.insight_id in by_id and by_id[row.insight_id] != row:
                    raise ValueError("Conflicting records for one insight ID")
                by_id[row.insight_id] = row
                key = _insight_key(row)
                canonical.setdefault(key, row)
                replacements[row.insight_id] = canonical[key].insight_id
            section.insights = list(canonical.values())
            seen = set()
            retained = []
            for block in section.blocks:
                if block.insight_id:
                    block.insight_id = replacements[block.insight_id]
                    # Different IDs for the same original insight become one block.
                    block.evidence_ids = next(
                        row.evidence_ids
                        for row in section.insights
                        if row.insight_id == block.insight_id
                    )
                    key = (
                        "insight",
                        block.insight_id,
                        _normalized(block.title),
                        _normalized(block.text),
                        block.facts,
                    )
                else:
                    key = (
                        block.kind,
                        _normalized(block.title),
                        _normalized(block.text),
                        block.facts,
                        tuple(sorted(block.evidence_ids)),
                        tuple(block.trend_ids),
                    )
                if key not in seen:
                    seen.add(key)
                    retained.append(block)
            section.blocks = retained
        document.sections = [sync_section(section) for section in document.sections]
        document.metadata = IntelligenceMetadata.from_sections(document.sections)
