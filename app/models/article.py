"""Data models for raw articles fetched from external sources.

This module defines the canonical structure for unprocessed articles
ingested from various data sources (RSS, GitHub, etc.).
"""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class RawArticle:
    """Represents a raw, unprocessed article fetched from a source.

    This model serves as the standard output of the Fetchers layer
    and the input for the Processing layer.

    Attributes:
        title: The title of the article.
        url: The canonical URL of the article.
        content: The main content or summary of the article.
        published_date: The publication date (if available).
        source_name: The unique name of the source this article came from.
    """

    title: str
    url: str
    content: str
    published_date: datetime | None
    source_name: str
