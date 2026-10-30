"""Read API contracts, actual SQLite filtering and hostile HTTP boundaries."""

import threading
import time
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.config import WebConfig
from app.api.factory import WebServices, create_app
from app.models.knowledge_object import KnowledgeObject
from app.models.metadata import ExtractionResult
from app.services.repository.access_service import RepositoryAccessService
from app.services.repository.browse_service import BrowseService
from app.services.retrieval.retrieval_models import RetrievalResponse
from app.storage.knowledge.browse_store import SQLiteBrowseStore
from app.storage.knowledge.sqlite_store import SQLiteKnowledgeStore


@pytest.fixture
def bound(tmp_path):
    path = tmp_path / "private.db"
    store = SQLiteKnowledgeStore(path)
    when = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for i in range(4):
        store.save_objects(
            [
                KnowledgeObject(
                    id=str(i),
                    title=f"Title {i}",
                    source_type="rss" if i < 3 else "github",
                    source_name="source",
                    external_id=str(i),
                    source_url="https://example.org",
                    content_text=f"Text {i}",
                    content_hash=str(i),
                    fetched_at=when,
                    published_at=when if i < 3 else None,
                    created_at=when,
                    metadata=ExtractionResult(
                        summary="Summary",
                        topics=["AI"] if i < 2 else ["ML"],
                        entities=[],
                        relevance_score=0.8,
                    ),
                )
            ]
        )
    access = RepositoryAccessService(store)
    app_service = SimpleNamespace(get_knowledge_object=store.get_by_id)
    retrieval = Mock()
    retrieval.search.return_value = RetrievalResponse(query="AI")
    result = WebServices(app_service, BrowseService(access, SQLiteBrowseStore(path)), retrieval)
    yield result
    store.close()


def client(bound=None, **config):
    return TestClient(
        create_app(bound, config=WebConfig(_env_file=None, **config)),
        base_url="http://localhost",
        raise_server_exceptions=False,
    )


def test_schema_export_needs_no_services():
    app = create_app(config=WebConfig(_env_file=None))
    schema = app.openapi()
    assert "/api/v1/knowledge" in schema["paths"]
    assert "WEB_PASSWORD" not in str(schema)
    assert client().get("/api/v1/ready").status_code == 503
    assert client().get("/api/v1/health").json() == {"status": "ok"}


def test_filtered_count_ties_and_null_last(bound):
    api = client(bound)
    first = api.post("/api/v1/knowledge/search", json={"source_types": ["rss"], "limit": 1}).json()
    second = api.get("/api/v1/knowledge?source_types=rss&limit=1&offset=1").json()
    assert first["total"] == 3
    assert first["items"][0]["id"] == "0"
    assert second["items"][0]["id"] == "1"
    assert second["page_info"]["has_prev"]
    topics = api.post(
        "/api/v1/knowledge/search", json={"topics": ["AI"], "source_types": ["rss"]}
    ).json()
    assert topics["total"] == 2
    assert api.get("/api/v1/knowledge?sort_direction=asc").json()["items"][-1]["id"] == "3"
    assert (
        api.post("/api/v1/knowledge/search", json={"source_names": ["' OR 1=1 --"]}).json()["total"]
        == 0
    )
    assert api.get("/api/v1/knowledge?offset=50").json()["items"] == []


@pytest.mark.parametrize(
    "payload",
    [
        {"limit": 0},
        {"limit": 101},
        {"offset": -1},
        {"topics": ["x"] * 51},
        {"sort_field": "title; DROP TABLE knowledge_objects"},
        {"unknown": "secret-sentinel"},
        {"published_after": "2026-02-01T00:00:00Z", "published_before": "2026-01-01T00:00:00Z"},
        {"published_after": "2026-01-01T00:00:00"},
    ],
)
def test_invalid_queries_hide_rejected_input(bound, payload):
    response = client(bound).post("/api/v1/knowledge/search", json=payload)
    assert response.status_code == 422
    assert response.json() == {"detail": "Invalid request"}


def test_public_detail_and_missing_items(bound):
    api = client(bound)
    result = api.get("/api/v1/knowledge/0")
    assert result.status_code == 200
    assert result.json()["fetched_at"]
    assert "embedding_vector" not in result.json()
    assert "vector_db_id" not in result.json()
    assert api.get("/api/v1/knowledge/missing").status_code == 404
    assert api.get("/api/v1/knowledge/missing/related").status_code == 404


def test_statistics_schema_and_cached_digest_reads(bound):
    api = client(bound)
    assert api.get("/api/v1/statistics").json()["total_items"] == 4
    assert len(api.get("/api/v1/source-health").json()) == 2
    assert api.get("/api/v1/digest/history").json() == []
    assert api.get("/api/v1/digest/latest").status_code == 404
    assert api.get("/api/v1/digest?date=2026-01-01").status_code == 404
    assert api.get("/api/v1/digest?date=bad").status_code == 422
    assert api.get("/api/v1/schema/table").json()["version"] == 1
    assert api.get("/api/v1/schema/script").status_code == 404


def test_retrieval_rejects_unsupported_filters(bound):
    api = client(bound)
    assert api.post("/api/v1/retrieval/search", json={"query": "AI"}).status_code == 200
    for method in ("keyword", "hybrid"):
        assert (
            api.post(
                "/api/v1/retrieval/search",
                json={"query": "AI", "method": method, "filters": {"topics": ["AI"]}},
            ).status_code
            == 400
        )
    response = api.post(
        "/api/v1/retrieval/search",
        json={"query": "AI", "method": "vector", "filters": {"topics": ["AI"]}},
    )
    assert response.status_code == 200
    assert bound.retrieval.search.call_args.kwargs["metadata_filter"].topics == ["AI"]


def test_auth_protects_data_schema_and_docs(bound):
    api = client(bound, username="owner", password="long-password-for-tests", docs_enabled=True)
    for path in ("/api/v1/knowledge", "/api/v1/openapi.json", "/api/v1/docs", "/api/v1/health"):
        assert api.get(path).status_code == 401
        assert api.get(path, auth=("owner", "wrong")).status_code == 401
        assert api.get(path, auth=("owner", "long-password-for-tests")).status_code == 200


def test_host_origin_cors_and_files(bound):
    api = client(bound)
    assert api.get("/api/v1/health", headers={"host": "attacker.example"}).status_code == 400
    assert (
        api.get("/api/v1/health", headers={"origin": "https://attacker.example"}).status_code == 403
    )
    assert (
        api.post(
            "/api/v1/knowledge/search", headers={"sec-fetch-site": "cross-site"}, json={}
        ).status_code
        == 403
    )
    preflight = api.options(
        "/api/v1/knowledge",
        headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST"},
    )
    assert preflight.headers["access-control-allow-origin"] == "http://localhost:5173"
    for path in ("/.env", "/.env.web", "/data/private.db", "/app/config/settings.py"):
        assert api.get(path).status_code == 404
    response = api.get("/api/v1/health")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["cache-control"] == "no-store"


def test_large_body_and_safe_internal_error(bound):
    api = client(bound)
    assert api.post("/api/v1/knowledge/search", content=b"x" * 65537).status_code == 413
    bound.browse.search = Mock(side_effect=RuntimeError("API_KEY=secret /private/database.db"))
    response = api.post("/api/v1/knowledge/search", json={})
    assert response.status_code == 500
    assert "secret" not in response.text and "database" not in response.text


def test_sync_read_runs_off_event_loop(bound):
    api = client(bound)
    started = threading.Event()
    release = threading.Event()
    original = bound.browse.search

    def slow(query):
        started.set()
        release.wait(3)
        return original(query)

    bound.browse.search = slow
    with api:
        thread = threading.Thread(target=lambda: api.get("/api/v1/knowledge"))
        thread.start()
        assert started.wait(2)
        try:
            start = time.monotonic()
            assert api.get("/api/v1/health").status_code == 200
            assert time.monotonic() - start < 1
        finally:
            release.set()
            thread.join()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"host": "0.0.0.0"},
        {"username": "owner"},
        {"origins": ["*"]},
        {"allowed_hosts": ["*"]},
        {"origins": ["http://localhost/path"]},
    ],
)
def test_insecure_config_rejected(kwargs):
    with pytest.raises(ValidationError):
        WebConfig(_env_file=None, **kwargs)
