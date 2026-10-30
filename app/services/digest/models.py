"""Cached daily snapshots; selection dates and intelligence cohorts are explicit."""

from datetime import timedelta
from typing import Literal

from pydantic import AwareDatetime, Field, model_validator

from app.services.digest.config import Category, DigestConfig
from app.services.intelligence.context import sync_section
from app.services.intelligence.models import Citation, Contract, IntelligenceDocument, day_start


def validate_refined_document(document: IntelligenceDocument) -> IntelligenceDocument:
    """Revalidate a structured refined document, including its rendered provenance."""
    result = IntelligenceDocument.model_validate(document.model_dump())
    if result.refined_at is None:
        raise ValueError("Run intelligence refinement before saving or generating a digest")
    ids: list[str] = []
    for section in result.sections:
        if sync_section(section) != section:
            raise ValueError("Intelligence content/provenance does not match its blocks")
        ids.extend(block.block_id for block in section.blocks)
    if len(ids) != len(set(ids)):
        raise ValueError("Intelligence block IDs must be unique")
    return result


class DigestItem(Citation):
    """One live source selected by publication date, or fetched_at when absent.

    Naive legacy timestamps are explicitly interpreted as UTC. The stored
    publication date remains None when missing; fetched_at is never relabeled.
    """

    summary: str
    source_type: str = Field(min_length=1)
    source_name: str = Field(min_length=1)
    published_at: AwareDatetime | None
    fetched_at: AwareDatetime
    date_basis: Literal["published_at", "fetched_at"]
    assumed_utc: bool = False
    importance_score: float = Field(ge=0, le=1)
    score_computed_at: AwareDatetime
    topics: list[str]

    @model_validator(mode="after")
    def validate_basis(self) -> "DigestItem":
        """Keep fallback semantics and topic identities unambiguous."""
        expected = "published_at" if self.published_at is not None else "fetched_at"
        if self.date_basis != expected:
            raise ValueError("Digest date basis does not match source timestamps")
        if len(set(self.topics)) != len(self.topics) or any(not t.strip() for t in self.topics):
            raise ValueError("Topics must be unique and nonblank")
        return self


class DigestSection(Contract):
    """Editorial category is separate from each item's original source_type."""

    section_id: str = Field(min_length=1)
    section_title: str = Field(min_length=1)
    category: Category
    items: list[DigestItem] = Field(min_length=1, max_length=5)


def topic_groups(sections: list[DigestSection]) -> dict[str, list[str]]:
    """Build groups only from displayed items, preserving display order."""
    groups: dict[str, list[str]] = {}
    for section in sections:
        for item in section.items:
            for topic in item.topics:
                groups.setdefault(topic, []).append(item.knowledge_id)
    return groups


class DailyDigest(Contract):
    """Immutable-by-policy archive, rebuilt only on an explicit request.

    Intelligence uses the UTC fetched cohort from S22. Item selection uses the
    requested UTC publication day with fetched_at fallback, so the two scopes
    may differ. Cache reads do not refresh either scope or call an LLM.
    """

    digest_id: str = Field(min_length=1)
    digest_date: str
    started_at: AwareDatetime
    generated_at: AwareDatetime
    total_items: int = Field(ge=0)
    candidate_count: int = Field(ge=0)
    eligible_count: int = Field(ge=0)
    unmapped_count: int = Field(ge=0)
    sections: list[DigestSection]
    topic_groups: dict[str, list[str]]
    intelligence: IntelligenceDocument
    config: DigestConfig

    @model_validator(mode="after")
    def validate_digest(self) -> "DailyDigest":
        """Reject inconsistent dates, totals, policy decisions and references."""
        start = day_start(self.digest_date)
        if start > self.started_at or self.generated_at < self.started_at:
            raise ValueError("Invalid digest execution times")
        doc = validate_refined_document(self.intelligence)
        if (
            doc.date != self.digest_date
            or doc.refined_at is None
            or doc.refined_at > self.started_at
        ):
            raise ValueError("Digest requires an already refined document for the same day")
        if len({s.category for s in self.sections}) != len(self.sections):
            raise ValueError("Digest categories must be unique")
        if len({s.section_id for s in self.sections}) != len(self.sections):
            raise ValueError("Section IDs must be unique")
        items = [item for section in self.sections for item in section.items]
        if self.total_items != len(items) or len({i.knowledge_id for i in items}) != len(items):
            raise ValueError("Digest totals and unique item IDs must match")
        if (
            not self.total_items
            <= self.eligible_count
            <= self.candidate_count - self.unmapped_count
        ):
            raise ValueError("Invalid selection counts")
        if self.topic_groups != topic_groups(self.sections):
            raise ValueError("Topic groups must reference exactly the displayed items")
        for section in self.sections:
            if len(section.items) > self.config.max_items_per_section:
                raise ValueError("Section exceeds configured limit")
            for item in section.items:
                when = item.published_at or item.fetched_at
                category, threshold = self.config.selection(item.source_type, item.source_name)
                if not start <= when < start + timedelta(days=1) or when > self.started_at:
                    raise ValueError("Item falls outside the requested day or is in the future")
                if item.fetched_at > self.started_at or item.score_computed_at > self.started_at:
                    raise ValueError("Item prerequisites are from the future")
                if (
                    category != section.category
                    or threshold is None
                    or item.importance_score < threshold
                ):
                    raise ValueError("Item does not satisfy the saved digest policy")
        return self
