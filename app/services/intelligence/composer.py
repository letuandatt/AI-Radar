"""Compose cited, structured reports that can be refined without parsing Markdown."""

import json
from collections.abc import Callable
from datetime import datetime, timezone
from uuid import uuid4

from app.core.logger import get_logger
from app.integrations.llm.provider import LLMProvider
from app.prompts.builder import PromptBuilder
from app.prompts.loader import PromptLoader
from app.services.intelligence.context import (
    displayed_trends,
    load_day,
    load_ranking,
    resolve_citation,
    sync_section,
    unique_citations,
)
from app.services.intelligence.models import (
    Citation,
    ContentBlock,
    ExecutiveSummary,
    IntelligenceDocument,
    IntelligenceMetadata,
    IntelligenceSection,
)
from app.services.repository.access_service import RepositoryAccessService
from app.services.trend.ranker import TrendRanker

logger = get_logger(__name__)


class IntelligenceComposer:
    """Sync composition API; async callers must offload the whole call.

    Blocks retain prose-to-source mapping. Trend tables and score facts are
    rendered by code and remain fixed during refinement. No upstream jobs run.
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

    def compose(self, date: str) -> IntelligenceDocument:
        """Compose four sections with explicit empty states and immutable source facts."""
        now = self._clock()
        logger.info("Intelligence composition START: date=%s", date)
        day = load_day(self._access, date, now)
        run, saved = self._access.read_insight_report(date)
        if run is None:
            raise LookupError(f"No insight run for {date}; run insight generation first")
        ranking = load_ranking(self._access, date, now)
        selected = saved[:5]
        for insight in selected:
            for citation in insight.citations:
                if resolve_citation(self._access, citation.knowledge_id) != citation:
                    raise ValueError("Saved insight source changed; regenerate insights")
        notable = day.candidates[:10]
        notable_citations = [resolve_citation(self._access, row.item.id) for row in notable]
        sources = unique_citations(
            [citation for insight in selected for citation in insight.citations] + notable_citations
        )
        allowed = {row.knowledge_id: row for row in sources}
        trend_rows = displayed_trends(ranking)
        trend_citations: list[Citation] = []
        for trend in trend_rows:
            if not trend.sample_knowledge_ids:
                raise LookupError(f"No saved sample evidence for trend: {trend.trend_id}")
            trend_citations.extend(
                resolve_citation(self._access, key) for key in trend.sample_knowledge_ids
            )
        trend_citations = unique_citations(trend_citations)
        document_id = str(uuid4())
        summary_blocks = []
        if allowed:
            payload = {
                "report_date": date,
                "insights": [
                    {
                        "title": row.title,
                        "description": row.description,
                        "evidence_ids": row.evidence_ids,
                    }
                    for row in selected
                ],
                "notable_items": [
                    {
                        "knowledge_id": row.item.id,
                        "title": row.item.title[:300],
                        "summary": row.item.metadata.summary[:1000],
                        "importance": row.score.final_score,
                    }
                    for row in notable
                ],
            }
            prompt = (
                PromptBuilder(self._prompts.load("intelligence/composition"))
                .with_untrusted_data(json.dumps(payload, ensure_ascii=False, allow_nan=False))
                .build()
            )
            logger.info(
                "Intelligence composition LLM: insights=%d, notable=%d", len(selected), len(notable)
            )
            output = self._provider.structured_chat(prompt, ExecutiveSummary)
            summary = ExecutiveSummary.model_validate(output.model_dump())
            for index, sentence in enumerate(summary.sentences):
                if not set(sentence.evidence_ids) <= allowed.keys():
                    raise ValueError("Summary selected unknown evidence IDs")
                summary_blocks.append(
                    ContentBlock(
                        block_id=f"{document_id}:summary:{index}",
                        kind="prose",
                        text=sentence.text,
                        evidence_ids=sentence.evidence_ids,
                    )
                )
        else:
            summary_blocks.append(
                ContentBlock(
                    block_id=f"{document_id}:summary:empty",
                    kind="notice",
                    text="No daily candidates or saved insights are available for this report. "
                    "Insight generation completed successfully with an empty result. "
                    "This does not establish complete ingestion or absence of real-world activity.",
                )
            )
        trend_blocks = [
            ContentBlock(
                block_id=f"{document_id}:trends",
                kind="fixed" if trend_rows else "notice",
                text=TrendRanker.generate_summary_markdown(ranking),
                evidence_ids=[row.knowledge_id for row in trend_citations],
                trend_ids=[row.trend_id for row in trend_rows],
            )
        ]
        key_blocks = [
            ContentBlock(
                block_id=f"{document_id}:insight:{row.insight_id}",
                kind="prose",
                title=row.title,
                text=row.description,
                evidence_ids=row.evidence_ids,
                insight_id=row.insight_id,
            )
            for row in selected
        ] or [
            ContentBlock(
                block_id=f"{document_id}:insights:empty",
                kind="notice",
                text="No evidence-backed insights were produced by the successful generation run.",
            )
        ]
        notable_blocks = [
            ContentBlock(
                block_id=f"{document_id}:item:{row.item.id}",
                kind="prose",
                text=row.item.metadata.summary[:1000] or "No saved summary.",
                facts=f"Importance {row.score.final_score:.3f}; "
                f"score computed {row.score.computed_at.isoformat()}.",
                evidence_ids=[row.item.id],
            )
            for row in notable
        ] or [
            ContentBlock(
                block_id=f"{document_id}:notable:empty",
                kind="notice",
                text="No scored items in this UTC fetched_at cohort.",
            )
        ]
        sections = [
            IntelligenceSection(
                section_id=f"{document_id}:summary",
                section_type="executive_summary",
                title="Executive Summary",
                content="Pending render.",
                citations=sources,
                blocks=summary_blocks,
            ),
            IntelligenceSection(
                section_id=f"{document_id}:trends",
                section_type="top_trends",
                title="Top Trends",
                content="Pending render.",
                citations=trend_citations,
                blocks=trend_blocks,
            ),
            IntelligenceSection(
                section_id=f"{document_id}:insights",
                section_type="key_insights",
                title="Key Insights",
                content="Pending render.",
                insights=selected,
                citations=unique_citations([c for row in selected for c in row.citations]),
                blocks=key_blocks,
            ),
            IntelligenceSection(
                section_id=f"{document_id}:notable",
                section_type="notable_items",
                title="Notable Items",
                content="Pending render.",
                citations=notable_citations,
                blocks=notable_blocks,
            ),
        ]
        sections = [sync_section(section) for section in sections]
        if self._access.read_insight_report(date) != (run, saved):
            raise RuntimeError("Insight report changed during composition; retry")
        for citation in unique_citations([c for section in sections for c in section.citations]):
            if resolve_citation(self._access, citation.knowledge_id) != citation:
                raise ValueError("Citation source changed during composition; retry")
        result = IntelligenceDocument(
            document_id=document_id,
            date=date,
            generated_at=self._clock(),
            sections=sections,
            metadata=IntelligenceMetadata.from_sections(sections),
        )
        logger.info(
            "Intelligence composition DONE: date=%s, citations=%d",
            date,
            result.metadata.total_citations,
        )
        return result
