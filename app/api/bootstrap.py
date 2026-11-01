"""Bridge initialized repository components to the HTTP adapter."""

from app.api.config import WebConfig
from app.api.factory import WebServices, create_app
from app.api.server import WebServer
from app.services.feedback.service import FeedbackService
from app.services.repository.access_service import RepositoryAccessService
from app.services.repository.browse_service import BrowseService
from app.storage.knowledge.browse_store import SQLiteBrowseStore


def start_web(
    initializer,
    app_service,
    retrieval,
    config: WebConfig,
    *,
    llm_chain=None,
    importance_config=None,
) -> WebServer:
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
    access = RepositoryAccessService(initializer.sqlite_store)
    manual_add = None
    if llm_chain is not None:
        from app.prompts.loader import PromptLoader
        from app.services.analysis.content_analyzer import ContentAnalyzer
        from app.services.extraction.content_sanitizer import ContentSanitizer
        from app.services.extraction.metadata_extractor import MetadataExtractor
        from app.services.importance.scorer import ImportanceScorer
        from app.services.knowledge.manual_add_service import ManualAddService
        from app.services.knowledge.url_fetcher import PublicPageFetcher

        manual_add = ManualAddService(
            app_service,
            access,
            PublicPageFetcher(),
            MetadataExtractor(llm_chain, ContentSanitizer(), max_concurrent=1),
            ContentAnalyzer(access, llm_chain, PromptLoader(), max_concurrent=1),
            ImportanceScorer(access, llm_chain, importance_config),
        )
    bound = WebServices(
        app_service,
        BrowseService(
            access,
            SQLiteBrowseStore(initializer.config.sqlite_path),
        ),
        retrieval,
        manual_add,
        FeedbackService(access),
    )
    return WebServer(
        create_app(bound, config=config, subscribers=subscribers, webhook_secret=secret), config
    ).start()
