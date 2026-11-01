"""Feedback API persistence and the existing HTTP security boundary."""

from dataclasses import replace
from unittest.mock import Mock, patch

import pytest

from app.api.bootstrap import start_web
from app.api.config import WebConfig
from app.services.feedback.service import FeedbackService
from tests.api.test_routes import bound as bound
from tests.api.test_routes import client


@pytest.fixture
def api(bound):
    return client(replace(bound, feedback=FeedbackService(bound.browse.access)))


def test_get_put_clear_preferences_and_idempotency(api):
    path = "/api/v1/knowledge/0/feedback"
    assert api.get(path).json()["rating"] is None
    first = api.put(path, json={"rating": "useful"})
    assert first.status_code == 200
    assert api.put(path, json={"rating": "useful"}).json() == first.json()
    assert api.get(path).json() == first.json()
    prefs = api.get("/api/v1/feedback/preferences").json()
    assert prefs == {"rated_items": 1, "topics": [{"topic": "ai", "useful": 1, "not_useful": 0}]}
    assert api.put(path, json={"rating": None}).json()["rating"] is None
    assert api.get("/api/v1/feedback/preferences").json()["rated_items"] == 0


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"rating": True},
        {"rating": 1},
        {"rating": "like"},
        {"rating": "useful", "user_id": "other"},
    ],
)
def test_invalid_contract(api, body):
    assert api.put("/api/v1/knowledge/0/feedback", json=body).status_code == 422
    assert api.get("/api/v1/knowledge/0/feedback").json()["rating"] is None


def test_auth_origin_content_type_and_size(bound):
    bound = replace(bound, feedback=FeedbackService(bound.browse.access))
    path = "/api/v1/knowledge/0/feedback"
    auth = client(bound, username="reader", password="long-local-password")
    assert auth.put(path, json={"rating": "useful"}).status_code == 401
    assert auth.get("/api/v1/feedback/preferences").status_code == 401
    api = client(bound)
    assert (
        api.put(
            path, json={"rating": "useful"}, headers={"origin": "https://evil.example"}
        ).status_code
        == 403
    )
    assert api.put(
        path, content='{"rating":"useful"}', headers={"content-type": "text/plain"}
    ).status_code in {415, 422}
    assert (
        api.put(
            path, content=b"x" * 65537, headers={"content-type": "application/json"}
        ).status_code
        == 413
    )
    assert api.get(path).json()["rating"] is None


def test_missing_unbound_and_sanitized_errors(api, bound):
    assert api.get("/api/v1/knowledge/missing/feedback").status_code == 404
    assert api.put("/api/v1/knowledge/missing/feedback", json={"rating": None}).status_code == 404
    assert client(bound).get("/api/v1/knowledge/0/feedback").status_code == 503
    broken = Mock()
    broken.record_feedback.side_effect = RuntimeError("database secret")
    response = client(replace(bound, feedback=broken)).put(
        "/api/v1/knowledge/0/feedback", json={"rating": "useful"}
    )
    assert response.status_code == 500 and "secret" not in response.text


def test_web_bootstrap_binds_feedback_without_llm(bound):
    initializer = Mock(sqlite_store=bound.browse.access._store)
    initializer.config.sqlite_path = bound.browse.access._store.conn_manager.db_path
    with patch("app.api.bootstrap.WebServer") as server:
        start_web(initializer, bound.app_service, None, WebConfig(_env_file=None))
    service = server.call_args.args[0].state.services.feedback
    assert service.get_feedback("0").rating is None


def test_put_preflight_requires_an_allowed_origin(api):
    headers = {
        "origin": "http://localhost:5173",
        "access-control-request-method": "PUT",
        "access-control-request-headers": "content-type",
    }
    path = "/api/v1/knowledge/0/feedback"
    response = api.options(path, headers=headers)
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == headers["origin"]
    headers["origin"] = "https://evil.example"
    assert api.options(path, headers=headers).status_code == 400
