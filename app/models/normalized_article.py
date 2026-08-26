"""Data model for normalized articles.

This module defines the unified schema for articles after normalization,
regardless of their original source (RSS, GitHub, HuggingFace).
"""

from datetime import datetime

from pydantic import BaseModel, Field


class NormalizedArticle(BaseModel):
    """Represents an article after normalization.

    This is the unified schema that all articles conform to after passing
    through the normalization pipeline (Sprint 10). It serves as the input
    for metadata extraction (Sprint 11) and Knowledge Object construction (Sprint 12).

    Attributes:
        article_id: Unique identifier, computed as SHA-256 hash of (url + title).
        title: Standardized article title.
        content: Standardized article content (HTML stripped, whitespace normalized).
        url: Standardized article URL.
        source_name: Name of the source (e.g., "techcrunch", "fastapi").
        source_type: Type of source ("rss", "github", "huggingface").
        author: Article author (optional, may be None).
        published_date: Publication date in UTC (optional, may be None).
        fetched_at: Timestamp when the article was fetched.
        raw_content_hash: Hash of the original content, used for traceability.
    """

    article_id: str = Field(..., description="Unique identifier (SHA-256 of url + title)")
    title: str = Field(..., description="Standardized article title")
    content: str = Field(..., description="Standardized article content")
    url: str = Field(..., description="Standardized article URL")
    source_name: str = Field(..., description="Name of the source")
    source_type: str = Field(..., description="Type of source: rss, github, huggingface")
    author: str | None = Field(default=None, description="Article author (optional)")
    published_date: datetime | None = Field(default=None, description="Publication date in UTC")
    fetched_at: datetime | None = Field(
        default=None, description="Timestamp when article was fetched"
    )
    raw_content_hash: str = Field(..., description="Hash of original content for traceability")
