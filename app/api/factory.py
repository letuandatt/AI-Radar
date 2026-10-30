"""Dependency-injected API factory. Importing/exporting schema opens no database."""

import logging
import sqlite3
from dataclasses import dataclass

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api.config import WebConfig
from app.api.security import SecurityBoundary
from app.api.v1.models import ApiError
from app.api.v1.routes import router
from app.services.app_service import ApplicationService
from app.services.email.subscriber_service import SubscriberService
from app.services.repository.browse_service import BrowseService
from app.services.repository.query_models import InvalidQueryError, RepositoryError
from app.services.retrieval.retrieval_models import RetrievalError
from app.services.retrieval.retrieval_service import RetrievalService


@dataclass(frozen=True)
class WebServices:
    """Runtime references are private server state, never serialized."""

    app_service: ApplicationService
    browse: BrowseService
    retrieval: RetrievalService | None = None


def create_app(
    services: WebServices | None = None,
    *,
    config: WebConfig | None = None,
    subscribers: SubscriberService | None = None,
    webhook_secret: str = "",
) -> FastAPI:
    """Create a bound app, or an offline schema-only app with unavailable data routes."""
    config = config or WebConfig()
    app = FastAPI(
        title="AI-Radar",
        version="0.5.0",
        debug=False,
        openapi_url="/api/v1/openapi.json",
        docs_url="/api/v1/docs" if config.docs_enabled else None,
        redoc_url=None,
    )
    app.state.services = services
    app.state.app_service = services.app_service if services else None
    app.include_router(
        router,
        responses={code: {"model": ApiError} for code in (400, 401, 403, 404, 413, 422, 500, 503)},
    )
    if subscribers is not None:
        from app.api.routes.email_webhook import create_router

        app.include_router(create_router(subscribers, webhook_secret), include_in_schema=False)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, error: RequestValidationError):
        return JSONResponse({"detail": "Invalid request"}, 422)

    @app.exception_handler(Exception)
    async def safe_error(request: Request, error: Exception):
        # Do not log URLs, authorization, request bodies or exception payloads.
        logging.getLogger(__name__).error("API operation failed (%s)", type(error).__name__)
        code = (
            400
            if isinstance(error, InvalidQueryError)
            else 503
            if isinstance(error, (RepositoryError, RetrievalError, sqlite3.Error))
            else 500
        )
        return JSONResponse(
            {"detail": "Invalid query" if code == 400 else "Service unavailable"},
            code,
            headers={"Cache-Control": "no-store"},
        )

    app.add_middleware(SecurityBoundary, config=config)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.origins,
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "Authorization"],
    )
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=config.allowed_hosts)
    return app
