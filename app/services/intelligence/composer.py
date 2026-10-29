"""Compose an unrefined report using saved insights and current persisted inputs."""

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
    links,
    load_day,
    load_ranking,
    plain,
    resolve_citation,
    unique_citations,
)
from app.services.intelligence.models import (
    ExecutiveSummary,
    IntelligenceDocument,
    IntelligenceMetadata,
    IntelligenceSection,
)
from app.services.repository.access_service import RepositoryAccessService
from app.services.trend.ranker import TrendRanker

logger = get_logger(__name__)


class IntelligenceComposer:
    """Sync API used by the local runner; async callers must use to_thread.

    Composition does not generate insights or rerun upstream analysis/scoring.
    It combines the saved daily insights with current saved scores/trends. Source
    drift on a saved insight is an error requiring regeneration, not a silent edit.
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
        """Return four cited sections; missing runs fail, successful empty runs do not."""
        now = self._clock()
        logger.info("Intelligence composition START: date=%s", date)
        day = load_day(self._access, date, now)
        run, saved = self._access.read_insight_report(date)
        if run is None:
            raise LookupError(f"No insight run for {date}; run insight generation first")
        ranking = load_ranking(self._access, date, now)
        selected = saved[:5]  # Repository order: confidence descending, then ID.
        for insight in selected:
            for citation in insight.citations:
                if resolve_citation(self._access, citation.knowledge_id) != citation:
                    raise ValueError("Saved insight source changed; regenerate insights")
        notable = day.candidates[:10]
        notable_citations = [resolve_citation(self._access, row.item.id) for row in notable]
        summary_sources = unique_citations(
            [citation for insight in selected for citation in insight.citations] + notable_citations
        )
        allowed = {row.knowledge_id: row for row in summary_sources}
        summary_citations = []
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
            paragraphs = []
            for sentence in summary.sentences:
                if not set(sentence.evidence_ids) <= allowed.keys():
                    raise ValueError("Summary selected unknown evidence IDs")
                citations = [allowed[key] for key in sentence.evidence_ids]
                summary_citations.extend(citations)
                paragraphs.append(f"{plain(sentence.text)} {links(citations)}")
            summary_text = " ".join(paragraphs)
        else:
            summary_text = (
                "No daily candidates or saved insights are available for this report. "
                "The insight generation run completed successfully with an empty result. "
                "This does not establish complete ingestion or absence of real-world activity."
            )
        trend_rows = displayed_trends(ranking)
        trend_citations = []
        trend_evidence = []
        for trend in trend_rows:
            citations = [resolve_citation(self._access, key) for key in trend.sample_knowledge_ids]
            trend_citations.extend(citations)
            trend_evidence.append(
                f"- {plain(trend.name)}: {links(citations) or 'No saved sample sources.'}"
            )
        trend_text = TrendRanker.generate_summary_markdown(ranking)
        if trend_evidence:
            trend_text += "\n### Saved sample sources\n\n" + "\n".join(trend_evidence)
        key_text = (
            "\n\n".join(
                f"### {plain(row.title)}\n\n{plain(row.description)}\n\n{links(row.citations)}"
                for row in selected
            )
            or "No evidence-backed insights were produced by the successful generation run."
        )
        notable_text = (
            "\n".join(
                f"- {links([citation])} — importance {row.score.final_score:.3f}; "
                f"score computed {row.score.computed_at.isoformat()}. "
                f"{plain(row.item.metadata.summary[:1000])}"
                for row, citation in zip(notable, notable_citations, strict=True)
            )
            or "No scored items in this UTC fetched_at cohort."
        )
        document_id = str(uuid4())
        sections = [
            IntelligenceSection(
                section_id=f"{document_id}:summary",
                section_type="executive_summary",
                title="Executive Summary",
                content=summary_text,
                citations=unique_citations(summary_citations),
            ),
            IntelligenceSection(
                section_id=f"{document_id}:trends",
                section_type="top_trends",
                title="Top Trends",
                content=trend_text,
                citations=unique_citations(trend_citations),
                trend_ids=[row.trend_id for row in trend_rows],
            ),
            IntelligenceSection(
                section_id=f"{document_id}:insights",
                section_type="key_insights",
                title="Key Insights",
                content=key_text,
                insights=selected,
                citations=unique_citations([c for row in selected for c in row.citations]),
            ),
            IntelligenceSection(
                section_id=f"{document_id}:notable",
                section_type="notable_items",
                title="Notable Items",
                content=notable_text,
                citations=notable_citations,
            ),
        ]
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
