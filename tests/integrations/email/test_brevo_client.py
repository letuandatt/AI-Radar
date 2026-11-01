"""HTTP fakes only; never submit mail to a real provider."""

import json

import httpx
import pytest

from app.integrations.email.brevo_client import BrevoEmailClient, EmailSendError


def send(handler, pauses=None):
    return BrevoEmailClient(
        "secret",
        sender_email="sender@example.com",
        transport=httpx.MockTransport(handler),
        pause=(pauses if pauses is not None else []).append,
    ).send_digest(
        "reader@example.com",
        "Digest",
        "<body>Hello</body>",
        "https://radar.example.com/unsubscribe?t=abc",
        plain="Hello",
        idempotency_key="stable",
    )


def test_payload_and_unsubscribe():
    def handler(request):
        body = json.loads(request.content)
        assert request.headers["api-key"] == "secret"
        assert len(body["to"]) == 1
        assert body["headers"]["idempotencyKey"] == "stable"
        assert "Unsubscribe" in body["htmlContent"] and "Unsubscribe:" in body["textContent"]
        assert body["htmlContent"].endswith("</body>")
        return httpx.Response(201, json={"messageId": "message-1"})

    assert send(handler) == "message-1"


@pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
def test_transient_retry_keeps_same_payload(status):
    bodies, pauses = [], []

    def handler(request):
        bodies.append(request.content)
        return httpx.Response(status if len(bodies) < 3 else 201, json={"messageId": "ok"})

    assert send(handler, pauses) == "ok"
    assert len(bodies) == 3 and bodies[0] == bodies[1] == bodies[2]
    assert pauses == [1, 2]


@pytest.mark.parametrize("status", [400, 401, 403, 422])
def test_permanent_error_is_not_retried(status):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(status, json={"message": "private recipient data"})

    with pytest.raises(EmailSendError) as result:
        send(handler)
    assert not result.value.unknown and "private" not in str(result.value)
    assert len(calls) == 1


@pytest.mark.parametrize("kind,unknown", [(httpx.ConnectError, False), (httpx.ReadTimeout, True)])
def test_transport_error_classification(kind, unknown):
    calls = []

    def handler(request):
        calls.append(1)
        raise kind("transport failure", request=request)

    with pytest.raises(EmailSendError) as result:
        send(handler)
    assert result.value.unknown is unknown and len(calls) == 3


def test_duplicate_response_is_not_claimed_as_delivery():
    with pytest.raises(EmailSendError) as result:
        send(lambda request: httpx.Response(400, json={"code": "duplicate_parameter"}))
    assert result.value.unknown


@pytest.mark.parametrize("payload", [{}, {"messageId": ""}, {"messageId": None}])
def test_bad_success_response_is_unknown(payload):
    with pytest.raises(EmailSendError) as result:
        send(lambda request: httpx.Response(201, json=payload))
    assert result.value.unknown


def test_long_retry_after_does_not_sleep():
    pauses = []
    with pytest.raises(EmailSendError):
        send(lambda request: httpx.Response(429, headers={"Retry-After": "3600"}), pauses)
    assert pauses == []
