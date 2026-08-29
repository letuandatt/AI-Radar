"""Data model for Knowledge Objects - the core unit of knowledge in AI-Radar.

This is the foundational model and represents the "brick"
that all later layers (Vector DB, RAG, Daily Digest, MCP) will interact with.
"""

import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, Field

from .metadata import ExtractionResult


class KnowledgeObject(BaseModel):
    """Represents a standardized, validated unit of knowledge.

    This model provides:
    - Provenance tracking (source_type, source_name, external_id)
    - Content hashing for deduplication
    - Pipeline version tracking for re-processing decisions
    - Stealth integration fields for future Vector DB operations

    Attributes:
        id: System-generated UUID for internal tracking
        source_type: Type of source ("rss", "github", "huggingface")
        source_name: Name of the source (e.g., "techcrunch")
        external_id: External ID from source (e.g., NormalizedArticle.article_id)
        source_url: Original URL of the article
        content_hash: SHA-256 hash of content_text for deduplication
        fetched_at: When the article was fetched
        published_at: When the article was published (if available)
        parser_version: Version of the fetcher/parser used
        normalizer_version: Version of the normalizer used
        extractor_version: Version of the LLM extractor used
        title: Article title
        content_text: Normalized article content
        metadata: LLM-extracted metadata (ExtractionResult)
        embedding_vector: Placeholder for Vector DB integration
        vector_db_id: Placeholder for Vector DB integration
        created_at: When this KnowledgeObject was created
        updated_at: When this KnowledgeObject was last updated
    """

    # System generated
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="System-generated UUID")

    # Provenance & Identity (DATA-001)
    source_type: str = Field(..., description="Source type: rss, github, huggingface")
    source_name: str = Field(..., description="Name of the source")
    external_id: str = Field(
        ..., description="External ID from the source (e.g., NormalizedArticle.article_id)"
    )
    source_url: str = Field(..., description="Original URL")

    content_hash: str = Field(..., description="SHA-256 hash of the normalized content")
    fetched_at: datetime = Field(..., description="When the article was fetched")
    published_at: datetime | None = Field(
        default=None, description="When the article was published"
    )

    # Pipeline Version Tracking
    parser_version: str = Field(default="1.0.0", description="Version of the parser/fetcher")
    normalizer_version: str = Field(default="1.0.0", description="Version of the normalizer")
    extractor_version: str = Field(default="1.0.0", description="Version of the LLM extractor")

    # Core Content
    title: str = Field(..., description="Article title")
    content_text: str = Field(..., description="Normalized article content")
    metadata: ExtractionResult = Field(..., description="LLM-extracted metadata")

    # Stealth Integration for Vector DB
    embedding_vector: list[float] | None = Field(default=None, description="Embedding vector")
    vector_db_id: str | None = Field(default=None, description="ID in the vector DB")

    # Timestamps
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When this KnowledgeObject was created",
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When this KnowledgeObject was last updated",
    )
