"""Data models for data sources.

This module defines the canonical structures representing external data sources
that the system can ingest data from.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class RSSSource:
    """Represents an RSS feed source configuration.

    Attributes:
        name: A unique, human-readable identifier for the source.
        url: The URL of the RSS feed.
        is_active: Whether the source is currently enabled for fetching.
    """

    name: str
    url: str
    is_active: bool = True
