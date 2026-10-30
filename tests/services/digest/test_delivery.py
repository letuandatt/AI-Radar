"""Delivery retry isolation: no generation and no real network calls."""

from unittest.mock import MagicMock

from app.integrations.email.brevo_client import EmailSendError
from app.services.digest.delivery import DigestDeliveryService
from tests.services.digest.test_generator import digest_env as digest_env
from tests.services.email.test_subscriber_service import subscribers as subscribers
from tests.services.intelligence.conftest import DAY
from tests.services.intelligence.conftest import environment as environment
from tests.services.intelligence.test_refiner import prepared as prepared


def service_for(subscribers):
    client = MagicMock()
    client.send_digest.return_value = "message-id"
    return DigestDeliveryService(subscribers, client, "https://radar.example.com"), client


def test_accepted_is_not_submitted_again(digest_env, subscribers):
    digest = digest_env[3].generate(DAY)
    subscribers.subscribe("reader@example.com")
    service, client = service_for(subscribers)
    assert service.deliver_all(digest)[0].status == "accepted"
    assert service.deliver_all(digest)[0].status == "accepted"
    client.send_digest.assert_called_once()
    subscribers.deactivate("reader@example.com")
    assert service.deliver_all(digest) == []


def test_failed_recipient_does_not_resend_successes(digest_env, subscribers):
    digest = digest_env[3].generate(DAY)
    subscribers.subscribe("a@example.com")
    subscribers.subscribe("b@example.com")
    service, client = service_for(subscribers)
    client.send_digest.side_effect = ["accepted-a", EmailSendError("Rejected"), "accepted-b"]
    assert [r.status for r in service.deliver_all(digest)] == ["accepted", "failed"]
    assert [r.status for r in service.deliver_all(digest)] == ["accepted", "accepted"]
    assert client.send_digest.call_count == 3


def test_unknown_stays_blocked(digest_env, subscribers):
    digest = digest_env[3].generate(DAY)
    subscribers.subscribe("reader@example.com")
    service, client = service_for(subscribers)
    client.send_digest.side_effect = EmailSendError("Timeout", unknown=True)
    assert service.deliver_all(digest)[0].status == "unknown"
    assert service.deliver_all(digest)[0].status == "unknown"
    assert client.send_digest.call_count == 1


def test_current_opt_out_and_channel_failure(digest_env, subscribers):
    digest = digest_env[3].generate(DAY)
    person = subscribers.subscribe("reader@example.com")
    service, client = service_for(subscribers)
    subscribers.deactivate(str(person.email))
    assert service.deliver_to_email(digest, [person])[0].status == "inactive"
    client.send_digest.assert_not_called()
    assert service.deliver_to_zalo(digest).status == "not_configured"
    channel = MagicMock(name="channel")
    channel.name = "fake-zalo"
    channel.send.return_value = False
    service.channel = channel
    assert service.deliver_to_zalo(digest).status == "failed"
    channel.send.return_value = True
    assert service.deliver_to_zalo(digest).status == "accepted"
