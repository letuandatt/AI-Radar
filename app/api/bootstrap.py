"""Bridge initialized repository components to the HTTP adapter."""

from app.api.config import WebConfig
from app.api.factory import WebServices, create_app
from app.api.server import WebServer
from app.services.repository.access_service import RepositoryAccessService
from app.services.repository.browse_service import BrowseService
from app.storage.knowledge.browse_store import SQLiteBrowseStore


def start_web(initializer, app_service, retrieval, config: WebConfig) -> WebServer:
    """Reuse existing services; optional callbacks keep their existing route paths."""
    subscribers, secret = None, ""
    if config.email_callbacks_enabled:
        from app.services.email.config import EmailConfig
        from app.services.email.subscriber_service import SubscriberService
        from app.storage.knowledge.email_store import EmailStore

        email = EmailConfig()
        secret = email.webhook_secret.get_secret_value()
        subscribers = SubscriberService(
            EmailStore(initializer.config.sqlite_path), email.soft_bounce_limit
        )
    bound = WebServices(
        app_service,
        BrowseService(
            RepositoryAccessService(initializer.sqlite_store),
            SQLiteBrowseStore(initializer.config.sqlite_path),
        ),
        retrieval,
    )
    return WebServer(
        create_app(bound, config=config, subscribers=subscribers, webhook_secret=secret), config
    ).start()
