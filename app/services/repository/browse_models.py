"""Bounded page-based read contracts; no database or provider configuration."""

from typing import Annotated, Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from app.models.metadata import ExtractionResult
from app.services.repository.query_models import KnowledgeItemSummary, PageInfo

Label = Annotated[str, Field(min_length=1, max_length=200)]


class BrowseQuery(BaseModel):
    """AND across fields, OR within lists; inclusive UTC publication bounds.

    Null publication dates sort last. ID breaks ties. Each request observes one
    database snapshot; page offsets can shift when writers change the dataset.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    source_types: list[Label] = Field(default_factory=list, max_length=20)
    source_names: list[Label] = Field(default_factory=list, max_length=50)
    topics: list[Label] = Field(default_factory=list, max_length=50)
    published_after: AwareDatetime | None = None
    published_before: AwareDatetime | None = None
    sort_field: Literal["published_at", "created_at", "source_type", "title"] = "published_at"
    sort_direction: Literal["asc", "desc"] = "desc"
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0, le=100000)

    @model_validator(mode="after")
    def ordered_dates(self) -> Self:
        """Reject inverted publication intervals."""
        if self.published_after and self.published_before:
            if self.published_after > self.published_before:
                raise ValueError("Publication bounds are reversed")
        return self


class BrowseItem(KnowledgeItemSummary):
    """Editorial relevance is distinct from retrieval ranking."""

    relevance_score: float = Field(ge=0, le=1)


class BrowsePage(BaseModel):
    """An exact filtered count and one ordered page from the same snapshot."""

    items: list[BrowseItem] = Field(default_factory=list)
    total: int
    page_info: PageInfo


class BrowseDetail(BaseModel):
    """Only public content and provenance; arbitrary internal metadata is excluded."""

    id: str
    title: str
    source_type: str
    source_name: str
    source_url: str
    content_text: str
    metadata: ExtractionResult
    fetched_at: AwareDatetime
    published_at: AwareDatetime | None
    created_at: AwareDatetime
    updated_at: AwareDatetime
