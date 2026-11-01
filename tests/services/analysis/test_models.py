"""Tests for content analysis models."""

from datetime import timedelta, timezone

import pytest
from pydantic import ValidationError

from app.services.analysis.models import (
    AnalysisEntities,
    ContentAnalysisOutput,
    ContentAnalysisResult,
    CrossSourceCoverage,
    CrossSourceGroup,
)
from tests.fakes.analysis import NOW


class TestContentAnalysisOutput:
    """Tests for ContentAnalysisOutput validation."""

    def test_valid_output(self) -> None:
        output = ContentAnalysisOutput(
            themes=["RAG", "Retrieval"],
            entities=AnalysisEntities(
                models=["GPT-4"],
                companies=["OpenAI"],
                people=["Sam Altman"],
            ),
            sentiment="positive",
            key_claims=["RAG improves accuracy by 30%"],
            technical_depth="intermediate",
            confidence=0.87,
        )
        assert output.themes == ["RAG", "Retrieval"]
        assert output.sentiment == "positive"
        assert output.confidence == 0.87

    def test_empty_themes_allowed_at_schema_level(self) -> None:
        """Schema allows empty themes; ContentAnalyzer validates."""
        output = ContentAnalysisOutput(
            themes=[],
            entities=AnalysisEntities(),
            sentiment="neutral",
            key_claims=["Claim"],
            technical_depth="beginner",
            confidence=0.5,
        )
        assert output.themes == []

    def test_invalid_sentiment_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ContentAnalysisOutput(
                themes=["AI"],
                entities=AnalysisEntities(),
                sentiment="unknown",
                key_claims=["Claim"],
                technical_depth="beginner",
                confidence=0.5,
            )

    def test_confidence_out_of_range_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ContentAnalysisOutput(
                themes=["AI"],
                entities=AnalysisEntities(),
                sentiment="positive",
                key_claims=["Claim"],
                technical_depth="beginner",
                confidence=1.5,
            )

    def test_max_themes_enforced(self) -> None:
        with pytest.raises(ValidationError):
            ContentAnalysisOutput(
                themes=["A", "B", "C", "D", "E", "F"],
                entities=AnalysisEntities(),
                sentiment="neutral",
                key_claims=["Claim"],
                technical_depth="beginner",
                confidence=0.5,
            )


class TestContentAnalysisResult:
    """Tests for ContentAnalysisResult."""

    def test_from_output(self) -> None:
        output = ContentAnalysisOutput(
            themes=["RAG"],
            entities=AnalysisEntities(models=["GPT-4"]),
            sentiment="positive",
            key_claims=["Claim 1"],
            technical_depth="advanced",
            confidence=0.9,
        )

        result = ContentAnalysisResult.from_output("ko-123", output)

        assert result.knowledge_id == "ko-123"
        assert result.analyzed_at is not None
        assert result.analyzed_at.tzinfo is not None
        assert result.themes == ["RAG"]
        assert result.entities.models == ["GPT-4"]
        assert result.sentiment == "positive"
        assert result.confidence == 0.9

    def test_from_output_sets_utc_timestamp(self) -> None:
        output = ContentAnalysisOutput(
            themes=["AI"],
            entities=AnalysisEntities(),
            sentiment="neutral",
            key_claims=["Claim"],
            technical_depth="beginner",
            confidence=0.5,
        )

        result = ContentAnalysisResult.from_output("ko-456", output)

        assert result.analyzed_at.tzinfo == timezone.utc


@pytest.mark.parametrize(
    "changes",
    [
        {"source_count": 1},
        {"source_count": 3},
        {"knowledge_ids": ["a", "a"]},
        {"sources": ["rss:a", "rss:a"]},
        {"coverage_score": 1.1},
        {"first_seen": NOW + timedelta(seconds=1)},
        {"first_seen": NOW.replace(tzinfo=None)},
    ],
)
def test_cross_source_group_rejects_invalid_membership(changes):
    data = dict(
        group_id="group",
        topic="theme:rag",
        knowledge_ids=["a", "b"],
        source_count=2,
        sources=["rss:a", "rss:b"],
        first_seen=NOW,
        last_seen=NOW,
        coverage_score=1.0,
    )
    with pytest.raises(ValidationError):
        CrossSourceGroup(**(data | changes))


@pytest.mark.parametrize(
    "changes",
    [
        {"article_count": 3},
        {"source_count": 1},
        {"total_sources": 1},
        {"coverage_score": 0.5},
        {"first_seen": None},
        {"last_seen": NOW - timedelta(seconds=1)},
        {"time_window_days": 0},
    ],
)
def test_cross_source_coverage_rejects_inconsistent_statistics(changes):
    data = dict(
        topic="theme:rag",
        time_window_days=7,
        knowledge_ids=["a", "b"],
        sources=["rss:a", "rss:b"],
        article_count=2,
        source_count=2,
        total_sources=2,
        coverage_score=1.0,
        first_seen=NOW,
        last_seen=NOW,
    )
    with pytest.raises(ValidationError):
        CrossSourceCoverage(**(data | changes))
