"""Authentication, replay handling and scanner-safe unsubscribe callbacks."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes.email_webhook import create_router
from tests.services.email.test_subscriber_service import subscribers as subscribers

SECRET = "test-secret-" * 4


def client_for(subscribers):
    app = FastAPI()
    app.include_router(create_router(subscribers, SECRET))
    return TestClient(app)


def test_auth_payload_and_replay(subscribers):
    subscribers.subscribe("reader@example.com")
    client = client_for(subscribers)
    event = {"email": "reader@example.com", "event": "soft_bounce", "message-id": "m1", "id": 123}
    url = "/api/webhook/brevo"
    headers = {"X-Brevo-Secret": SECRET}
    assert client.post(url, json=event).status_code == 401
    assert client.post(url, json=event, headers=headers).json()["applied"] == 1
    assert client.post(url, json=event, headers=headers).json()["applied"] == 0
    event["message-id"] = "m2"
    assert client.post(url, json=event, headers=headers).json()["applied"] == 1
    assert client.post(url, json={}, headers=headers).status_code == 422
    assert client.post(url, content=b"x" * 65537, headers=headers).status_code == 413
    assert subscribers.store.get("reader@example.com")["soft_bounces"] == 2


def test_unsubscribe_get_does_not_mutate(subscribers):
    subscribers.subscribe("reader@example.com")
    client = client_for(subscribers)
    url = subscribers.unsubscribe_link("reader@example.com", "https://testserver")
    response = client.get(url)
    assert response.status_code == 200 and "Confirm unsubscribe" in response.text
    assert response.headers["referrer-policy"] == "no-referrer"
    assert len(subscribers.list_active()) == 1
    assert client.post(url).status_code == 200
    assert subscribers.list_active() == []
    assert client.get("/api/email/unsubscribe?token=<script>").status_code == 422
