"""Data models for data sources.

This module defines the canonical structures representing external data sources
that the system can ingest data from.

All models use Pydantic BaseModel with frozen=True to ensure immutability
and enable JSON Schema generation for Schema-Driven UI.
"""

from enum import Enum

from pydantic import BaseModel, ConfigDict


class RSSSource(BaseModel):
    """Represents an RSS feed source configuration.

    Attributes:
        name: A unique, human-readable identifier for the source.
        url: The URL of the RSS feed.
        is_active: Whether the source is currently enabled for fetching.
    """

    model_config = ConfigDict(frozen=True)

    name: str
    url: str
    is_active: bool = True


class GitHubRepository(BaseModel):
    """Represents a GitHub repository source configuration.

    Attributes:
        name: A unique, human-readable identifier for the source.
        owner: The GitHub user or organization that owns the repository.
        repo: The repository name.
        is_active: Whether the source is currently enabled for fetching.
    """

    model_config = ConfigDict(frozen=True)

    name: str
    owner: str
    repo: str
    is_active: bool = True


class HFSourceType(str, Enum):
    """Defines the type of Hugging Face resource."""

    DATASET = "dataset"
    MODEL = "model"


class HFSource(BaseModel):
    """Represents a Hugging Face source configuration.

    Attributes:
        name: A unique, human-readable identifier for the source.
        resource_id: The Hugging Face resource identifier (e.g., 'username/repo_name').
        source_type: The type of resource (dataset or model).
        is_active: Whether the source is currently enabled for fetching.
    """

    model_config = ConfigDict(frozen=True)

    name: str
    resource_id: str
    source_type: HFSourceType
    is_active: bool = True
