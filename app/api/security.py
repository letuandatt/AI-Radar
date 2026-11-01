"""HTTP boundary: explicit origins, authentication, size limits and safe errors."""

import base64
import binascii
import hmac

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.api.config import WebConfig


class SecurityBoundary:
    """Protect all application paths, including docs; callbacks own their credentials."""

    def __init__(self, app: ASGIApp, config: WebConfig) -> None:
        self.app, self.config = app, config

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = dict(scope["headers"])
        path = scope["path"]
        origin = headers.get(b"origin", b"").decode("latin1")
        callback = path in {"/api/webhook/brevo", "/api/email/unsubscribe"}
        # Browsers must present a configured origin (or a true same-origin request).
        host = headers.get(b"host", b"").decode("latin1")
        same_origin = f"{scope['scheme']}://{host}"
        if not callback and origin and origin not in {*self.config.origins, same_origin}:
            await JSONResponse({"detail": "Origin not allowed"}, 403)(scope, receive, send)
            return
        if not callback and headers.get(b"sec-fetch-site") == b"cross-site":
            if origin not in self.config.origins:
                await JSONResponse({"detail": "Cross-site request denied"}, 403)(
                    scope, receive, send
                )
                return
        if self.config.username and not callback:
            provided = headers.get(b"authorization", b"")
            expected = f"{self.config.username}:{self.config.password.get_secret_value()}".encode()
            try:
                scheme, encoded = provided.split(b" ", 1)
                valid = scheme.lower() == b"basic" and hmac.compare_digest(
                    base64.b64decode(encoded, validate=True), expected
                )
            except (ValueError, binascii.Error):
                valid = False
            if not valid:
                await JSONResponse(
                    {"detail": "Authentication required"},
                    401,
                    headers={"WWW-Authenticate": 'Basic realm="AI-Radar", charset="UTF-8"'},
                )(scope, receive, send)
                return
        # Buffer only bounded request bodies; chunked requests have the same limit.
        messages, size = [], 0
        while True:
            message = await receive()
            messages.append(message)
            size += len(message.get("body", b""))
            if size > 65536:
                await JSONResponse({"detail": "Request too large"}, 413)(scope, receive, send)
                return
            if message["type"] == "http.disconnect" or not message.get("more_body", False):
                break
        index = 0

        async def replay():
            nonlocal index
            if index < len(messages):
                message = messages[index]
                index += 1
                return message
            return await receive()

        async def secure_send(message):
            if message["type"] == "http.response.start":
                message["headers"] = [
                    *message.get("headers", []),
                    (b"cache-control", b"no-store"),
                    (b"x-content-type-options", b"nosniff"),
                    (b"referrer-policy", b"no-referrer"),
                    (b"x-frame-options", b"DENY"),
                ]
            await send(message)

        await self.app(scope, replay, secure_send)
