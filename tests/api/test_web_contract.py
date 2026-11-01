"""Coexistence with email routes and the exported client contract."""

import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.api.config import WebConfig
from app.api.factory import create_app
from app.services.email.subscriber_service import SubscriberService
from app.storage.knowledge.email_store import EmailStore
from app.storage.knowledge.sqlite_store import SQLiteKnowledgeStore


def test_email_callback_uses_its_own_authentication(tmp_path):
    path = tmp_path / "email.db"
    SQLiteKnowledgeStore(path).close()
    service = SubscriberService(EmailStore(path), soft_bounce_limit=3)
    config = WebConfig(_env_file=None, username="owner", password="long-password-for-tests")
    app = create_app(config=config, subscribers=service, webhook_secret="x" * 32)
    with TestClient(app, base_url="http://localhost") as api:
        assert api.get("/api/v1/health").status_code == 401
        response = api.post(
            "/api/webhook/brevo",
            headers={"X-Brevo-Secret": "x" * 32},
            json={"event": "delivered", "email": "reader@example.org", "message-id": "1"},
        )
        assert response.status_code == 200
        assert api.post("/api/webhook/brevo", json={}).status_code == 401
        assert api.get("/api/email/unsubscribe?token=" + "x" * 32).status_code == 200


def test_committed_schema_matches_app():
    expected = create_app(config=WebConfig(_env_file=None)).openapi()
    actual = json.loads((Path(__file__).resolve().parents[2] / "web/openapi.json").read_text())
    assert actual == expected
