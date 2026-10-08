"""Fixed, typed data for cross-source analysis tests."""

from datetime import datetime, timedelta, timezone

from app.models.knowledge_object import KnowledgeObject
from app.models.metadata import ExtractionResult
from app.services.analysis.models import AnalyzedKnowledgeItem

NOW = datetime(2026, 10, 9, 0, 0, tzinfo=timezone.utc)


def make_analysis(index=0, source="a", themes=None, entities=None, at=None, source_type="rss"):
    return AnalyzedKnowledgeItem(
        knowledge_id=f"ko-{index}",
        analyzed_at=at or NOW - timedelta(hours=1),
        source_type=source_type,
        source_name=source,
        themes=themes if themes is not None else ["RAG"],
        entities=entities or {},
        sentiment="neutral",
        key_claims=["Claim"],
        technical_depth="intermediate",
        confidence=0.8,
    )


def make_knowledge(analysis):
    return KnowledgeObject(
        id=analysis.knowledge_id,
        source_type=analysis.source_type,
        source_name=analysis.source_name,
        external_id=analysis.knowledge_id,
        source_url=f"https://example.com/{analysis.knowledge_id}",
        content_hash=analysis.knowledge_id,
        fetched_at=NOW,
        published_at=NOW - timedelta(days=100),
        title=f"Article {analysis.knowledge_id}",
        content_text="AI research evidence.",
        metadata=ExtractionResult(
            summary="Summary", topics=["AI"], entities=[], relevance_score=0.8
        ),
    )


def twenty_analyses():
    return [
        make_analysis(
            i,
            source="a" if i < 8 else "b" if i < 14 else "c",
            themes=[" RAG ", "rag"] if i < 14 else ["Vision"],
            entities={"companies": ["OpenAI"]} if i < 14 else {"models": ["OpenAI"]},
            at=NOW - timedelta(hours=i),
        )
        for i in range(20)
    ]
