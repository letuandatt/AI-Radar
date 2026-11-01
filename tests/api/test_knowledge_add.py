"""Write-route authentication, validation, safe errors and bootstrap wiring."""

from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.api.bootstrap import start_web
from app.api.config import WebConfig
from app.services.knowledge.models import ManualAddError, ManualAddResult
from tests.api.test_routes import bound as bound
from tests.api.test_routes import client


@pytest.fixture
def writer(bound):
    service = SimpleNamespace(
        add=AsyncMock(
            return_value=ManualAddResult(
                knowledge_id="id",
                status="created",
                indexing="ready",
                analysis="ready",
                importance="ready",
            )
        )
    )
    return replace(bound, manual_add=service)


def test_write_route_validates_and_does_not_expose_services(writer):
    api = client(writer)
    result = api.post("/api/v1/knowledge", json={"url": "https://example.org/article"})
    assert result.status_code == 200 and result.json()["knowledge_id"] == "id"
    assert set(result.json()) == {
        "knowledge_id",
        "status",
        "indexing",
        "analysis",
        "importance",
        "content_truncated",
    }
    for body in [
        {"url": "http://127.0.0.1"},
        {"url": "file:///etc/passwd"},
        {"url": "https://example.org", "api_key": "secret"},
        {"url": ""},
    ]:
        assert api.post("/api/v1/knowledge", json=body).status_code == 422
    writer.manual_add.add.assert_awaited_once()


def test_auth_origin_and_body_limits_precede_writes(writer):
    api = client(writer, username="reader", password="a-long-password-for-local")
    assert api.post("/api/v1/knowledge", json={"url": "https://example.org"}).status_code == 401
    api = client(writer)
    assert (
        api.post(
            "/api/v1/knowledge",
            json={"url": "https://example.org"},
            headers={"origin": "https://evil.example"},
        ).status_code
        == 403
    )
    assert (
        api.post(
            "/api/v1/knowledge", content=b"x" * 65537, headers={"content-type": "application/json"}
        ).status_code
        == 413
    )
    assert api.post(
        "/api/v1/knowledge",
        content='{"url":"https://example.org"}',
        headers={"content-type": "text/plain"},
    ).status_code in {415, 422}
    writer.manual_add.add.assert_not_awaited()


def test_busy_and_unbound_services_are_clear(writer, bound):
    writer.manual_add.add.side_effect = ManualAddError(409, "Another article is being added")
    assert (
        client(writer).post("/api/v1/knowledge", json={"url": "https://example.org"}).status_code
        == 409
    )
    writer.manual_add.add.side_effect = RuntimeError("provider secret")
    response = client(writer).post("/api/v1/knowledge", json={"url": "https://example.org"})
    assert response.status_code == 500 and "secret" not in response.text
    assert (
        client(bound).post("/api/v1/knowledge", json={"url": "https://example.org"}).status_code
        == 503
    )


def test_bootstrap_injects_one_shared_provider_without_calling_it(tmp_path):
    provider = Mock()
    initializer = SimpleNamespace(
        sqlite_store=Mock(), config=SimpleNamespace(sqlite_path=str(tmp_path / "db"))
    )
    with patch("app.api.bootstrap.WebServer") as server:
        start_web(initializer, Mock(), None, WebConfig(_env_file=None), llm_chain=provider)
    services = server.call_args.args[0].state.services
    assert services.manual_add is not None
    assert services.manual_add._extractor._llm_provider is provider
    assert services.manual_add._analyzer._llm_provider is provider
    assert services.manual_add._scorer._provider is provider
    provider.structured_chat.assert_not_called()
