"""Data models for metadata extraction results.

Defines the structured output schema that LLM must conform to
when extracting metadata from normalized articles.
"""

from pydantic import BaseModel, Field


class ExtractionResult(BaseModel):
    """Structured metadata extracted from an article by LLM.

    This model serves as the Pydantic schema for LLM structured output.
    The LLM is forced to return JSON matching this schema.

    Attributes:
        summary: Concise summary of the article content (max 200 words).
        topics: Main topics covered in the article (max 5).
        entities: Named entities (people, organizations, technologies).
        relevance_score: AI/tech industry relevance score (0.0 - 1.0).
    """

    summary: str = Field(
        ...,
        description="Concise summary of the article content, max 200 words",
    )

    topics: list[str] = Field(
        ...,
        description="Main topics covered in the article, max 5 items",
    )

    entities: list[str] = Field(
        ...,
        description="Named entities: people, organizations, technologies",
    )

    relevance_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Relevance score for AI/tech industry, between 0.0 and 1.0",
    )
