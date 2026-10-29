"""Bounded evidence loading shared by generation and composition."""

import html
import re
from datetime import datetime, timedelta
from urllib.parse import quote

from app.models.knowledge_object import KnowledgeObject
from app.services.analysis.models import ContentAnalysisResult, PatternSnapshot
from app.services.importance.models import ImportanceScore
from app.services.intelligence.models import Citation, Contract, day_start
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
