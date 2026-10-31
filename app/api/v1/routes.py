"""Thin read endpoints. All synchronous service calls run outside the event loop."""

import asyncio
from datetime import date
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request

from app.api.v1.models import DigestView, SchemaField, SearchRequest, Status, UISchema
from app.services.repository.browse_models import BrowseDetail, BrowsePage, BrowseQuery
from app.services.repository.query_models import RepositoryStatistics, SourceHealth
from app.services.retrieval.retrieval_models import RetrievalResponse

router = APIRouter(prefix="/api/v1")


def services(request: Request):
    """Reject unbound schema-only applications rather than creating dependencies."""
    bound = request.app.state.services
    if bound is None:
        raise HTTPException(503, "Services unavailable")
    return bound


@router.get("/health", operation_id="getHealth", response_model=Status)
async def health() -> Status:
    """Report API liveness only."""
    return Status(status="ok")


@router.get("/ready", operation_id="getReadiness", response_model=Status)
async def ready(request: Request) -> Status:
    """Probe repository reads without claiming pipeline health."""
    await asyncio.to_thread(services(request).browse.access.get_statistics)
    return Status(status="ready")


@router.get("/statistics", operation_id="getStatistics", response_model=RepositoryStatistics)
async def statistics(request: Request):
    """Return aggregate counts from the repository gateway."""
    return await asyncio.to_thread(services(request).browse.access.get_statistics)


@router.get("/source-health", operation_id="getSourceHealth", response_model=list[SourceHealth])
async def source_health(request: Request):
    """Return source counts and observation timestamps."""
    return await asyncio.to_thread(services(request).browse.access.get_source_health)


@router.get("/knowledge", operation_id="listKnowledge", response_model=BrowsePage)
async def knowledge(request: Request, query: Annotated[BrowseQuery, Query()]):
    """Read a bounded page with repeatable source/topic query parameters."""
    return await asyncio.to_thread(services(request).browse.search, query)


@router.post("/knowledge/search", operation_id="filterKnowledge", response_model=BrowsePage)
async def filter_knowledge(request: Request, query: BrowseQuery):
    """Read a bounded page using structured JSON filters."""
    return await asyncio.to_thread(services(request).browse.search, query)


@router.get("/knowledge/{item_id}", operation_id="getKnowledge", response_model=BrowseDetail)
async def detail(request: Request, item_id: str):
    """Return only typed content and provenance fields."""
    obj = await asyncio.to_thread(services(request).app_service.get_knowledge_object, item_id)
    if obj is None:
        raise HTTPException(404, "Knowledge item not found")
    return BrowseDetail.model_validate(obj.model_dump())


@router.get(
    "/knowledge/{item_id}/related", operation_id="getRelated", response_model=RetrievalResponse
)
async def related(request: Request, item_id: str, top_k: int = Query(default=3, ge=1, le=20)):
    """Find related items without exposing vectors or provider configuration."""
    bound = services(request)
    if bound.retrieval is None:
        raise HTTPException(503, "Retrieval unavailable")
    if await asyncio.to_thread(bound.app_service.get_knowledge_object, item_id) is None:
        raise HTTPException(404, "Knowledge item not found")
    return await asyncio.to_thread(bound.retrieval.get_related_items, item_id, top_k=top_k)


@router.post("/retrieval/search", operation_id="searchKnowledge", response_model=RetrievalResponse)
async def search(request: Request, body: SearchRequest):
    """Rank eligible live records; both retrieval branches apply the same ID restriction."""
    bound = services(request)
    if bound.retrieval is None:
        raise HTTPException(503, "Retrieval unavailable")

    query = body.filters or BrowseQuery()
    allowed = {"source_types", "source_names", "topics", "published_after", "published_before"}

    if body.filters is not None and body.filters.model_fields_set - allowed:
        raise HTTPException(400, "Ranking search does not accept pagination or sorting")

    candidate_ids = await asyncio.to_thread(bound.browse.matching_ids, query)
    result = await asyncio.to_thread(
        bound.retrieval.search,
        body.query,
        top_k=body.top_k,
        method=body.method,
        candidate_ids=candidate_ids,
    )

    return result.model_copy(
        update={
            "filters_applied": query.model_dump(mode="json", include=allowed, exclude_none=True)
            if body.filters is not None
            else None
        }
    )


async def saved_digest(request: Request, day: str) -> DigestView:
    """Read a cached digest without invoking generation or delivery."""
    result = await asyncio.to_thread(services(request).browse.access.get_digest, day)
    if result is None:
        raise HTTPException(404, "Saved digest not found")
    return DigestView.model_validate(result.model_dump())


@router.get("/digest", operation_id="getDigest", response_model=DigestView)
async def digest(request: Request, date: date):
    """Read the saved digest for an explicit UTC date."""
    return await saved_digest(request, date.isoformat())


@router.get("/digest/history", operation_id="getDigestHistory", response_model=list[str])
async def history(request: Request, limit: int = Query(default=30, ge=1, le=366)):
    """List available archive dates newest first."""
    return await asyncio.to_thread(services(request).browse.access.get_digest_history, limit)


@router.get("/digest/latest", operation_id="getLatestDigest", response_model=DigestView)
async def latest(request: Request):
    """Read the most recent saved digest."""
    dates = await asyncio.to_thread(services(request).browse.access.get_digest_history, 1)
    if not dates:
        raise HTTPException(404, "Saved digest not found")
    return await saved_digest(request, dates[0])


@router.get("/schema/{kind}", operation_id="getUISchema", response_model=UISchema)
async def schema(kind: str) -> UISchema:
    """Describe allowlisted field renderers for knowledge components."""
    definitions = {
        "table": [
            ("title", "Title", "text", False),
            ("source_type", "Source", "text", True),
            ("published_at", "Published", "date", True),
            ("topics", "Topics", "tags", False),
            ("relevance_score", "Relevance", "score", False),
        ],
        "filter": [
            ("source_types", "Sources", "multiselect", False),
            ("source_names", "Source names", "multiselect", False),
            ("topics", "Topics", "multiselect", False),
            ("published_at", "Publication dates", "date-range", False),
        ],
        "detail": [
            ("title", "Title", "text", False),
            ("source_name", "Source", "text", False),
            ("published_at", "Published", "date", False),
            ("fetched_at", "Collected", "date", False),
            ("summary", "Summary", "text", False),
            ("topics", "Topics", "tags", False),
            ("entities", "Entities", "tags", False),
            ("relevance_score", "AI relevance", "score", False),
            ("content_text", "Content", "text", False),
        ],
    }

    if kind not in definitions:
        raise HTTPException(404, "Schema not found")

    return UISchema(
        fields=[
            SchemaField.model_validate(dict(key=k, label=label, renderer=renderer, sortable=sort))
            for k, label, renderer, sort in definitions[kind]
        ]
    )
