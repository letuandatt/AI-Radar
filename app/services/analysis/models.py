"""Data models for content analysis results.

Defines the schema for LLM structured output and the full
analysis result including metadata fields set by the analyzer.
"""

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


class AnalysisEntities(BaseModel):
    """Named entities extracted from content analysis."""

    models: list[str] = Field(default_factory=list)
    companies: list[str] = Field(default_factory=list)
    people: list[str] = Field(default_factory=list)


class ContentAnalysisOutput(BaseModel):
    """Schema for LLM structured output.

    This is the subset of fields the LLM is expected to produce.
    The ContentAnalyzer wraps this into a full ContentAnalysisResult
    by adding knowledge_id and analyzed_at.
    """

    themes: list[str] = Field(
        default_factory=list,
        max_length=5,
        description="Up to 5 core themes, each 1-3 words.",
    )
    entities: AnalysisEntities = Field(
        default_factory=AnalysisEntities,
        description="Named entities: models, companies, people.",
    )
    sentiment: Literal["positive", "negative", "neutral"] = Field(
        description="Overall sentiment towards the AI/technology discussed.",
    )
    key_claims: list[str] = Field(
        default_factory=list,
        max_length=3,
        description="Up to 3 factual claims or key takeaways.",
    )
    technical_depth: Literal["beginner", "intermediate", "advanced"] = Field(
        description="Technical depth of the article.",
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence score for the analysis accuracy.",
    )


class ContentAnalysisResult(BaseModel):
    """Full content analysis result including metadata.

    This is the persisted form stored in the content_analyses table.
    """

    knowledge_id: str
    analyzed_at: datetime
    themes: list[str]
    entities: AnalysisEntities
    sentiment: Literal["positive", "negative", "neutral"]
    key_claims: list[str]
    technical_depth: Literal["beginner", "intermediate", "advanced"]
    confidence: float

    @classmethod
    def from_output(
        cls,
        knowledge_id: str,
        output: ContentAnalysisOutput,
    ) -> "ContentAnalysisResult":
        """Create a full result from LLM output."""
        return cls(
            knowledge_id=knowledge_id,
            analyzed_at=datetime.now(timezone.utc),
            themes=output.themes,
            entities=output.entities,
            sentiment=output.sentiment,
            key_claims=output.key_claims,
            technical_depth=output.technical_depth,
            confidence=output.confidence,
        )
