"""Bounded evidence loading shared by generation and composition."""

import html
import re
from datetime import datetime, timedelta
from urllib.parse import quote

from app.models.knowledge_object import KnowledgeObject
from app.services.analysis.models import ContentAnalysisResult, PatternSnapshot
from app.services.importance.models import ImportanceScore
from app.services.intelligence.models import (
    Citation,
    Contract,
    IntelligenceSection,
    day_start,
)
from app.services.repository.access_service import RepositoryAccessService
from app.services.trend.models import Trend, TrendRanking, week_label
from app.services.trend.ranker import TrendRanker


class Candidate(Contract):
    """One live day-cohort item with saved analysis and latest importance score."""

    item: KnowledgeObject
    analysis: ContentAnalysisResult
    score: ImportanceScore


class DailyInputs(Contract):
    """Up to 30 day candidates; ten most recently observed saved patterns."""

    total_items: int
    candidates: list[Candidate]
    patterns: list[PatternSnapshot]


def load_day(access: RepositoryAccessService, date: str, now: datetime) -> DailyInputs:
    """Reject future dates; parse saved prerequisite models before calling an LLM."""
    if now.utcoffset() is None or day_start(date) > now:
        raise ValueError("Expected an aware clock and a nonfuture report day")
    data = DailyInputs.model_validate(access.load_intelligence_inputs(date))
    for row in data.candidates:
        if row.item.id != row.analysis.knowledge_id or row.item.id != row.score.knowledge_id:
            raise ValueError("Candidate prerequisite identity mismatch")
    return data


def load_ranking(access: RepositoryAccessService, date: str, now: datetime) -> TrendRanking:
    """Require the newest complete ISO week ending at/before the report day start."""
    start = day_start(date)
    week = week_label(start - timedelta(days=start.weekday() + 7))
    return TrendRanker(access, clock=lambda: now).rank_trends(week)


def displayed_trends(ranking: TrendRanking) -> list[Trend]:
    """Unique trends actually rendered by the existing ranker's top-ten lists."""
    rows = [ranking.top_growing, ranking.top_declining, *ranking.top_by_type.values()]
    unique = {row.trend.trend_id: row.trend for group in rows for row in group[:10]}
    return sorted(unique.values(), key=lambda row: (-row.trend_score, row.trend_id))


def resolve_citation(access: RepositoryAccessService, identity: str) -> Citation:
    """Resolve a live source from SQLite, failing rather than inventing a URL."""
    item = access.get_knowledge_item(identity)
    if item is None or not item.source_url:
        raise LookupError(f"Missing live citation source: {identity}")
    return Citation(
        knowledge_id=item.id,
        title=item.title,
        source_url=item.source_url,
        relevance_score=item.metadata["relevance_score"],
    )


def unique_citations(rows: list[Citation]) -> list[Citation]:
    """Deduplicate references while preserving their first displayed order."""
    return list({row.knowledge_id: row for row in rows}.values())


def plain(value: str) -> str:
    """Escape untrusted text so it cannot create Markdown/HTML structure or links."""
    text = html.escape(" ".join(value.split()), quote=False)
    return re.sub(r"([\\`*_{}\[\]()#+.!|~:>\-])", r"\\\1", text)


def links(rows: list[Citation]) -> str:
    """Render validated source URLs with escaped labels and encoded delimiters."""
    return " ".join(
        f"[{plain(row.title)}]({quote(row.source_url, safe=':/?=&%#@+;,')})" for row in rows
    )


def render_section(section: IntelligenceSection) -> str:
    """Render blocks and their exact sources; only Composer fixed text is Markdown."""
    sources = {row.knowledge_id: row for row in section.citations}
    paragraphs = []
    for block in section.blocks:
        text = block.text if block.kind == "fixed" else plain(block.text)
        parts = [f"### {plain(block.title)}"] if block.title else []
        if block.facts:
            parts.append(plain(block.facts))
        parts.append(text)
        if block.evidence_ids:
            parts.append(links([sources[key] for key in block.evidence_ids]))
        paragraphs.append("\n\n".join(parts))
    return "\n\n".join(paragraphs)


def sync_section(section: IntelligenceSection) -> IntelligenceSection:
    """Derive rendered text and section metadata solely from retained blocks."""
    if not section.blocks:
        raise ValueError("Document has no content blocks; run composition again")
    sources: dict[str, Citation] = {}
    for citation in section.citations:
        if citation.knowledge_id in sources and sources[citation.knowledge_id] != citation:
            raise ValueError("Conflicting citation records")
        sources[citation.knowledge_id] = citation
    evidence = list(dict.fromkeys(key for block in section.blocks for key in block.evidence_ids))
    identities = list(
        dict.fromkeys(block.insight_id for block in section.blocks if block.insight_id)
    )
    insights = {row.insight_id: row for row in section.insights}
    if not set(evidence) <= sources.keys() or not set(identities) <= insights.keys():
        raise ValueError("Block references are missing from section provenance")
    for block in section.blocks:
        if block.insight_id and block.evidence_ids != insights[block.insight_id].evidence_ids:
            raise ValueError("Insight block evidence does not match original insight")
    result = section.model_copy(
        deep=True,
        update={
            "citations": [sources[key] for key in evidence],
            "insights": [insights[key] for key in identities],
            "trend_ids": list(
                dict.fromkeys(key for block in section.blocks for key in block.trend_ids)
            ),
        },
    )
    result.content = render_section(result)
    return result
