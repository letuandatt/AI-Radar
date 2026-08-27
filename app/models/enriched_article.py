"""Data model for enriched articles after metadata extraction.

Combines the NormalizedArticle with the ExtractionResult
to create a complete enriched representation.
"""

from pydantic import BaseModel, Field

from .metadata import ExtractionResult
from .normalized_article import NormalizedArticle


class EnrichedArticle(BaseModel):
    """Represents an article enriched with LLM-extracted metadata.

    This is the output of the MetadataExtractor and the input for
    Knowledge Object construction.

    Attributes:
        article: The original normalized article.
        extraction: The LLM-extracted metadata (None if extraction failed).
        extraction_status: Status of the extraction process.
        extraction_error: Error message if extraction failed.
    """

    article: NormalizedArticle = Field(
        ...,
        description="The original normalized article",
    )

    extraction: ExtractionResult | None = Field(
        default=None,
        description="LLM-extracted metadata (None if failed)",
    )

    extraction_status: str = Field(
        default="pending",
        description="Status: pending, success, failed, skipped",
    )

    extraction_error: str | None = Field(
        default=None,
        description="Error message if extraction failed",
    )
