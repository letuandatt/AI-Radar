"""Public HTTP contracts, independent of runtime secrets."""

from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.services.digest.models import DigestSection
from app.services.intelligence.models import IntelligenceDocument
from app.services.repository.browse_models import BrowseQuery


class Status(BaseModel):
    """API status, not acquisition pipeline health."""

    status: Literal["ok", "ready"]


class ApiError(BaseModel):
    """Safe error text; no exception details or rejected input values."""

    detail: str


class SearchRequest(BaseModel):
    """Ranking search; total_matches is returned candidates, not database total."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    query: str = Field(min_length=1, max_length=1000)
    top_k: int = Field(default=10, ge=1, le=50)
    method: Literal["hybrid", "keyword", "vector"] = "hybrid"
    filters: BrowseQuery | None = None


class DigestView(BaseModel):
    """Structured saved digest without internal scoring configuration."""

    digest_id: str
    digest_date: str
    generated_at: AwareDatetime
    total_items: int
    sections: list[DigestSection]
    topic_groups: dict[str, list[str]]
    intelligence: IntelligenceDocument


class SchemaField(BaseModel):
    """Only allowlisted renderer identifiers, never HTML or executable code."""

    key: str
    label: str
    renderer: Literal["text", "date", "tags", "score", "multiselect", "date-range"]
    sortable: bool = False


class UISchema(BaseModel):
    """Stable schema version for table/filter/detail consumers."""

    version: Literal[1] = 1
    fields: list[SchemaField]
