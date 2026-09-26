"""Tests for content analysis models."""

from datetime import timezone

import pytest
from pydantic import ValidationError

from app.services.analysis.models import (
    AnalysisEntities,
    ContentAnalysisOutput,
    ContentAnalysisResult,
)


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
