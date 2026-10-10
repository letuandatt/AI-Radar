"""Data models for content analysis results.

Defines the schema for LLM structured output and the full
analysis result including metadata fields set by the analyzer.
"""

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


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


class AnalyzedKnowledgeItem(ContentAnalysisResult):
    """Current analysis joined to the source identity of a live knowledge item."""

    analyzed_at: AwareDatetime
    source_type: str
    source_name: str


class CrossSourceGroup(BaseModel):
    """A normalized theme/entity mentioned by at least two distinct sources.

    Topic keys use theme:, models:, companies:, or people: namespaces.
    Source labels are URL-escaped source_type:source_name pairs.
    First/last seen refer to analysis timestamps, not publication timestamps.
    Coverage is window-relative: topic source count divided by distinct sources
    with at least one live analyzed item in the same analyzed_at window. Sources
    without such items are excluded, even if configured. A score of 1.0 means
    all observed sources mention the topic, not complete ingestion coverage.
    """

    group_id: str
    topic: str
    knowledge_ids: list[str] = Field(min_length=2)
    source_count: int = Field(ge=2)
    sources: list[str] = Field(min_length=2)
    first_seen: AwareDatetime
    last_seen: AwareDatetime
    coverage_score: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_membership(self) -> "CrossSourceGroup":
        """Reject inconsistent counts, duplicate members and reversed dates."""
        if len(set(self.knowledge_ids)) != len(self.knowledge_ids):
            raise ValueError("knowledge_ids must be unique")
        if len(set(self.sources)) != len(self.sources) or self.source_count != len(self.sources):
            raise ValueError("source_count must match unique sources")
        if self.source_count > len(self.knowledge_ids):
            raise ValueError("source_count cannot exceed item count")
        if self.first_seen > self.last_seen:
            raise ValueError("first_seen must not exceed last_seen")
        return self


class CrossSourceCoverage(BaseModel):
    """Coverage for one topic, including empty and single-source matches.

    total_sources counts distinct (source_type, source_name) pairs across live
    analyzed items in the requested analyzed_at window, regardless of topic.
    It is not the number of configured sources. coverage_score is source_count
    divided by this window-relative total, or 0.0 when that total is zero.
    The score measures topic presence among observed sources, not ingestion
    completeness, source reliability, or coverage outside the selected window.
    """

    topic: str
    time_window_days: int = Field(gt=0)
    knowledge_ids: list[str]
    sources: list[str]
    article_count: int = Field(ge=0)
    source_count: int = Field(ge=0)
    total_sources: int = Field(ge=0)
    coverage_score: float = Field(ge=0.0, le=1.0)
    first_seen: AwareDatetime | None
    last_seen: AwareDatetime | None

    @model_validator(mode="after")
    def validate_statistics(self) -> "CrossSourceCoverage":
        """Keep counts, coverage, and timestamps consistent with membership."""
        if self.article_count != len(set(self.knowledge_ids)) or self.article_count != len(
            self.knowledge_ids
        ):
            raise ValueError("article_count must match unique knowledge_ids")
        if self.source_count != len(set(self.sources)) or self.source_count != len(self.sources):
            raise ValueError("source_count must match unique sources")
        if self.source_count > min(self.total_sources, self.article_count):
            raise ValueError("source_count exceeds total_sources or article_count")
        expected = self.source_count / self.total_sources if self.total_sources else 0.0
        if abs(self.coverage_score - expected) > 1e-9:
            raise ValueError("coverage_score must equal source_count / total_sources")
        if self.article_count == 0:
            if self.first_seen is not None or self.last_seen is not None:
                raise ValueError("empty coverage must have no timestamps")
        elif (
            self.source_count == 0
            or self.first_seen is None
            or self.last_seen is None
            or self.first_seen > self.last_seen
        ):
            raise ValueError("non-empty coverage requires sources and ordered timestamps")
        return self


class ObservedKnowledgeItem(AnalyzedKnowledgeItem):
    """Current labels anchored to the first persisted analysis, not re-analysis."""

    first_observed_at: AwareDatetime
    confidence: float = Field(ge=0.0, le=1.0)


class DiscoveredPattern(BaseModel):
    """A deterministic pattern with an LLM-written explanation.

    metrics coverage is window-relative: current_source_count / total_sources,
    or 0.0 for an empty denominator. Both counts use live analyzed items in the
    current first_observed_at window; total_sources includes all topics, not all
    configured sources. This is topic presence, not ingestion completeness.
    Weekly metrics cover the newest consecutive 7-day intervals ending at
    window_end, not calendar weeks. weekly_window_days excludes the oldest
    partial interval; weekly_excluded_count counts its items in current_count.
    Older persisted records may lack these two explanatory weekly fields.
    """

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    pattern_id: str
    pattern_type: Literal["emerging", "recurring", "declining"]
    topic: str
    time_window_days: int = Field(ge=7)
    description: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_ids: list[str] = Field(min_length=1)
    first_detected: AwareDatetime
    metrics: dict[str, Any]

    @model_validator(mode="after")
    def unique_evidence(self) -> "DiscoveredPattern":
        """Prevent duplicate evidence from inflating support."""
        if len(self.evidence_ids) != len(set(self.evidence_ids)):
            raise ValueError("evidence_ids must be unique")
        return self


class PatternSnapshot(DiscoveredPattern):
    """One daily UTC observation; same-day runs replace the previous observation.

    Written only when the pattern is detected. Missing dates are not zero-count
    observations. History currently has no automatic retention or pruning.
    """

    observed_at: AwareDatetime

    @model_validator(mode="after")
    def ordered_observation(self) -> "PatternSnapshot":
        """A snapshot cannot precede the pattern's first detection."""
        if self.first_detected > self.observed_at:
            raise ValueError("observed_at must not precede first_detected")
        return self


class PatternDescription(BaseModel):
    """The only fields the LLM may produce for a precomputed candidate."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    pattern_id: str
    description: str = Field(min_length=1)


class PatternDescriptions(BaseModel):
    """Structured response for one bounded description batch."""

    model_config = ConfigDict(extra="forbid")
    descriptions: list[PatternDescription]
