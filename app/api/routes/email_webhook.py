"""Brevo callbacks and confirmed unsubscribe; reusable by the dashboard API."""

import asyncio
import hmac
import json
import sqlite3
from typing import Annotated

from fastapi import APIRouter, FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, EmailStr, Field, ValidationError

from app.services.email.subscriber_service import SubscriberService


class BrevoEvent(BaseModel):
    """The provider's id identifies a webhook, not a unique delivery event."""

    model_config = ConfigDict(str_strip_whitespace=True)
    event: str = Field(min_length=1, max_length=50)
    email: EmailStr
    message_id: str = Field(alias="message-id", min_length=1, max_length=512)


Token = Annotated[str, Query(min_length=32, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")]


def create_router(service: SubscriberService, secret: str) -> APIRouter:
    """Bind authenticated callbacks without storing request-specific global state."""
    if len(secret) < 32:
        raise ValueError("Webhook secret must contain at least 32 characters")
    router = APIRouter()

    @router.post("/api/webhook/brevo")
    async def brevo(request: Request) -> dict[str, int]:
        provided = request.headers.get("X-Brevo-Secret", "")
        if not hmac.compare_digest(provided.encode(), secret.encode()):
            raise HTTPException(401, "Invalid webhook credentials")
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 65536:
                raise HTTPException(413, "Webhook payload too large")
        try:
            payload = json.loads(body)
            events = payload if isinstance(payload, list) else [payload]
            if not 1 <= len(events) <= 100:
                raise ValueError("Expected 1 to 100 events")
            validated = [BrevoEvent.model_validate(event) for event in events]
        except (ValueError, ValidationError):
            raise HTTPException(422, "Invalid webhook payload")
        applied = 0
        try:
            for event in validated:
                applied += int(
                    await asyncio.to_thread(
                        service.handle_event, str(event.email), event.message_id, event.event
                    )
                )
        except sqlite3.OperationalError:
            raise HTTPException(429, "Storage busy; retry callback")
        return {"received": len(validated), "applied": applied}

    @router.get("/api/email/unsubscribe", response_class=HTMLResponse)
    async def confirm(token: Token) -> HTMLResponse:
        return HTMLResponse(
            "<!doctype html><html><body><h1>Unsubscribe from AI-Radar</h1>"
            '<form method="post" action="/api/email/unsubscribe?token=' + token + '">'
            '<button type="submit">Confirm unsubscribe</button></form></body></html>',
            headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"},
        )

    @router.post("/api/email/unsubscribe", response_class=HTMLResponse)
    async def unsubscribe(token: Token) -> HTMLResponse:
        await asyncio.to_thread(service.unsubscribe, token)
        return HTMLResponse(
            "Subscription disabled if the link was valid.",
            headers={
                "Cache-Control": "no-store",
                "Referrer-Policy": "no-referrer",
            },
        )

    return router


def create_app() -> FastAPI:
    """Standalone callback app; the shared dashboard API can include create_router."""
    from app.config.settings import get_settings
    from app.services.email.config import EmailConfig
    from app.storage.knowledge.email_store import EmailStore

    config = EmailConfig()
    service = SubscriberService(EmailStore(get_settings().sqlite_path), config.soft_bounce_limit)
    application = FastAPI(title="AI-Radar email callbacks", docs_url=None, redoc_url=None)
    application.include_router(create_router(service, config.webhook_secret.get_secret_value()))
    return application
