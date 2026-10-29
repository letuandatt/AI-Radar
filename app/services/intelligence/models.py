"""Daily intelligence contracts; report dates use UTC fetched_at cohorts.

Reruns use current saved analyses, scores and source records, not historical
as-of replay. Confidence is an uncalibrated LLM assessment. Two distinct item
citations do not necessarily represent two independent sources.
"""

from datetime import datetime, timedelta, timezone
from typing import Literal
from urllib.parse import urlsplit

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

InsightType = Literal["trend", "pattern", "connection", "warning"]
SectionType = Literal["executive_summary", "top_trends", "key_insights", "notable_items"]


def day_start(value: str) -> datetime:
    """Parse canonical YYYY-MM-DD as midnight UTC."""
    try:
        result = datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        if result.date().isoformat() != value:
            raise ValueError
        return result
    except (ValueError, TypeError) as error:
        raise ValueError("Expected a valid YYYY-MM-DD report date") from error


class Contract(BaseModel):
    """Reject unknown fields, nonfinite numbers and blank whitespace."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, str_strip_whitespace=True)


class Citation(Contract):
    """Source identity from SQLite; relevance_score is extraction relevance."""

    knowledge_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    source_url: str = Field(min_length=1)
    relevance_score: float = Field(ge=0, le=1)

    @field_validator("source_url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        """Only render absolute HTTP(S) source links without credentials."""
        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or any(ord(char) < 33 for char in value)
        ):
            raise ValueError("Citation requires an absolute HTTP(S) URL")
        return value


class InsightDraft(Contract):
    """LLM may select evidence and signal IDs, never source URLs or titles."""

    insight_type: InsightType
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=1800)
    evidence_ids: list[str] = Field(min_length=2, max_length=5)
    signal_ids: list[str] = Field(default_factory=list, max_length=5)
    confidence: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def validate_evidence(self) -> "InsightDraft":
        """Duplicate references cannot inflate support."""
        for values in (self.evidence_ids, self.signal_ids):
            if len(values) != len(set(values)) or any(not value.strip() for value in values):
                raise ValueError("Evidence and signal IDs must be unique and nonempty")
        if self.insight_type in {"trend", "pattern"} and not self.signal_ids:
            raise ValueError("Trend/pattern insights require persisted signal IDs")
        return self


class InsightBatch(Contract):
    """One bounded response; an empty list is a valid successful result."""

    insights: list[InsightDraft] = Field(max_length=10)


class Insight(InsightDraft):
    """Persisted insight, with report day separate from generation time."""

    insight_id: str = Field(min_length=1)
    report_date: str
    citations: list[Citation] = Field(min_length=2, max_length=5)
    generated_at: AwareDatetime

    @model_validator(mode="after")
    def validate_provenance(self) -> "Insight":
        """Keep ordered evidence and citations identical."""
        if day_start(self.report_date) > self.generated_at:
            raise ValueError("Report date cannot be in the future")
        if self.evidence_ids != [row.knowledge_id for row in self.citations]:
            raise ValueError("Citations must match ordered unique evidence_ids")
        return self


class InsightRun(Contract):
    """Successful day replacement, including zero insights; no row means never run.

    started_at prevents an older overlapping generation overwriting a newer run.
    candidate_count is bounded input size, not source ingestion completeness.
    """

    report_date: str
    started_at: AwareDatetime
    generated_at: AwareDatetime
    candidate_count: int = Field(ge=0, le=30)
    insight_count: int = Field(ge=0, le=10)
    trend_week: str

    @model_validator(mode="after")
    def validate_times(self) -> "InsightRun":
        """Reject future dates and reversed execution times."""
        from app.services.trend.models import week_start

        start = day_start(self.report_date)
        if start > self.started_at or self.generated_at < self.started_at:
            raise ValueError("Invalid insight run times")
        expected = start - timedelta(days=start.weekday() + 7)
        if week_start(self.trend_week) != expected:
            raise ValueError("Trend week must be the newest complete week before report day")
        return self


class SummarySentence(Contract):
    """One plain-text summary sentence with code-resolved citations."""

    text: str = Field(min_length=1, max_length=600)
    evidence_ids: list[str] = Field(min_length=1, max_length=5)

    @model_validator(mode="after")
    def unique_references(self) -> "SummarySentence":
        """Reject duplicated evidence references."""
        if len(self.evidence_ids) != len(set(self.evidence_ids)):
            raise ValueError("Summary evidence must be unique")
        return self


class ExecutiveSummary(Contract):
    """Three to five cited sentence blocks; factual support still needs review."""

    sentences: list[SummarySentence] = Field(min_length=3, max_length=5)


class IntelligenceSection(Contract):
    """Markdown with explicit supporting objects; empty states have no citations."""

    section_id: str
    section_type: SectionType
    title: str
    content: str = Field(min_length=1)
    insights: list[Insight] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    trend_ids: list[str] = Field(default_factory=list)


class IntelligenceMetadata(Contract):
    """Unique displayed IDs across sections; confidence averages unique insights."""

    total_insights: int = Field(ge=0)
    total_trends: int = Field(ge=0)
    total_citations: int = Field(ge=0)
    confidence_avg: float = Field(ge=0, le=1)

    @classmethod
    def from_sections(cls, sections: list[IntelligenceSection]) -> "IntelligenceMetadata":
        """Compute document totals without counting repeated citations/trends twice."""
        insights = {row.insight_id: row for section in sections for row in section.insights}
        return cls(
            total_insights=len(insights),
            total_trends=len({key for section in sections for key in section.trend_ids}),
            total_citations=len({row.knowledge_id for s in sections for row in s.citations}),
            confidence_avg=sum(row.confidence for row in insights.values()) / len(insights)
            if insights
            else 0.0,
        )


class IntelligenceDocument(Contract):
    """An unrefined four-section report; length optimization belongs to refinement."""

    document_id: str
    date: str
    generated_at: AwareDatetime
    sections: list[IntelligenceSection]
    metadata: IntelligenceMetadata

    @model_validator(mode="after")
    def validate_document(self) -> "IntelligenceDocument":
        """Require ordered sections, matching report dates and derived metadata."""
        if day_start(self.date) > self.generated_at:
            raise ValueError("Report date cannot be in the future")
        if [s.section_type for s in self.sections] != [
            "executive_summary",
            "top_trends",
            "key_insights",
            "notable_items",
        ]:
            raise ValueError("Expected the four ordered intelligence sections")
        if len({s.section_id for s in self.sections}) != 4:
            raise ValueError("Section IDs must be unique")
        if any(row.report_date != self.date for s in self.sections for row in s.insights):
            raise ValueError("Insight report date does not match document")
        if self.metadata != IntelligenceMetadata.from_sections(self.sections):
            raise ValueError("Metadata must match displayed sections")
        return self

    def to_markdown(self) -> str:
        """Render the complete document for local review/export."""
        return (
            f"# Daily intelligence — {self.date}\n\n"
            + "\n\n".join(f"## {section.title}\n\n{section.content}" for section in self.sections)
            + "\n"
        )
