"""Real SQLite + BM25 + in-memory Qdrant; no network, models or provider calls."""

import sqlite3
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import UUID

import pytest
from qdrant_client import QdrantClient
from qdrant_client.http import models

from app.api.factory import WebServices
from app.models.knowledge_object import KnowledgeObject
from app.models.metadata import ExtractionResult
from app.services.repository.access_service import RepositoryAccessService
from app.services.repository.browse_service import BrowseService
from app.services.retrieval.fusion_retriever import FusionRetriever
from app.services.retrieval.retrieval_service import RetrievalService
from app.services.retrieval.vector_search import VectorSearchService
from app.storage.knowledge.browse_store import SQLiteBrowseStore
from app.storage.knowledge.sqlite_store import SQLiteKnowledgeStore
from app.storage.search.bm25_index import BM25Document, BM25Index
from app.storage.vector.qdrant_store import QdrantVectorStore
from tests.api.test_routes import client


@pytest.fixture
def real_stack(tmp_path, monkeypatch):
    path = tmp_path / "knowledge.db"
    store = SQLiteKnowledgeStore(path)
    qdrant = QdrantClient(":memory:")

    qdrant.create_collection(
        "knowledge_objects",
        vectors_config=models.VectorParams(
            size=2,
            distance=models.Distance.COSINE,
        ),
    )

    monkeypatch.setattr("app.storage.vector.qdrant_store.QdrantClient", lambda **kw: qdrant)
    vector_store = QdrantVectorStore(dimensions=2)

    embedding = Mock()
    embedding.embed_text.return_value = [1.0, 0.0]

    vector = VectorSearchService(vector_store, embedding)
    bm25 = BM25Index()
    documents = []
    ids = [str(UUID(int=i + 1)) for i in range(5)]
    when = datetime(2026, 1, 1, tzinfo=timezone.utc)

    for i, kid in enumerate(ids):
        obj = KnowledgeObject(
            id=kid,
            title=f"Article {i}",
            source_type="rss" if i != 3 else "github",
            source_name="chosen" if i >= 2 else "other",
            external_id=kid,
            source_url="https://example.org",
            content_text="agents retrieval",
            content_hash=kid,
            fetched_at=when,
            published_at=when,
            metadata=ExtractionResult(
                summary="Summary", topics=["AI"], entities=[], relevance_score=0.9
            ),
        )

        store.save_objects([obj])
        documents.append(BM25Document(id=kid, text=obj.content_text, content_hash=kid))

        qdrant.upsert(
            "knowledge_objects",
            points=[
                models.PointStruct(
                    id=kid,
                    vector=[1.0, i / 10],
                    payload={"source_type": obj.source_type},
                )
            ],
        )

    bm25.build(documents)
    store.delete_by_id(ids[4])

    retrieval = RetrievalService(vector, FusionRetriever(vector, bm25), bm25, store)
    bound = WebServices(
        SimpleNamespace(get_knowledge_object=store.get_by_id),
        BrowseService(RepositoryAccessService(store), SQLiteBrowseStore(path)),
        retrieval,
    )

    yield bound, embedding, ids

    qdrant.close()
    store.close()


@pytest.mark.parametrize("method", ["keyword", "vector", "hybrid"])
def test_prefilter_before_top_k_and_multi_source(real_stack, method):
    bound, _, ids = real_stack

    response = client(bound).post(
        "/api/v1/retrieval/search",
        json={
            "query": "agents",
            "method": method,
            "top_k": 1,
            "filters": {
                "source_types": ["rss", "github"],
                "source_names": ["chosen"],
                "topics": ["AI"],
                "published_after": "2025-12-31T17:00:00-07:00",
                "published_before": "2026-01-01T00:00:00Z",
            },
        },
    )

    assert response.status_code == 200
    assert response.json()["total_matches"] == 1
    assert response.json()["results"][0]["knowledge_id"] in ids[2:4]


def test_empty_eligibility_skips_embedding_and_stale_index_rows(real_stack):
    bound, embedding, ids = real_stack
    api = client(bound)

    empty = api.post(
        "/api/v1/retrieval/search", json={"query": "agents", "filters": {"topics": ["missing"]}}
    )

    assert empty.json()["results"] == []
    embedding.embed_text.assert_not_called()

    result = api.post("/api/v1/retrieval/search", json={"query": "agents", "top_k": 50}).json()

    assert {item["knowledge_id"] for item in result["results"]} == set(ids[:4])


def test_outage_is_503_not_empty_success(real_stack):
    bound, embedding, _ = real_stack
    embedding.embed_text.side_effect = RuntimeError("private-provider-key")

    response = client(bound).post(
        "/api/v1/retrieval/search", json={"query": "agents", "method": "vector"}
    )

    assert response.status_code == 503
    assert "private-provider-key" not in response.text


def test_inclusive_end_of_day_does_not_include_next_midnight(real_stack, tmp_path):
    bound, _, ids = real_stack

    with sqlite3.connect(tmp_path / "knowledge.db") as db:
        db.execute(
            "UPDATE knowledge_objects SET published_at=? WHERE id=?",
            (
                "2026-01-01T23:59:59.999999+00:00",
                ids[0],
            ),
        )
        db.execute(
            "UPDATE knowledge_objects SET published_at=? WHERE id=?",
            (
                "2026-01-02T00:00:00+00:00",
                ids[1],
            ),
        )

    filters = {"source_names": ["other"], "published_before": "2026-01-01T23:59:59.999999Z"}
    api = client(bound)

    page = api.post("/api/v1/knowledge/search", json=filters).json()
    assert [item["id"] for item in page["items"]] == [ids[0]]

    ranked = api.post(
        "/api/v1/retrieval/search",
        json={
            "query": "agents",
            "method": "keyword",
            "filters": filters,
        },
    ).json()

    assert [item["knowledge_id"] for item in ranked["results"]] == [ids[0]]
