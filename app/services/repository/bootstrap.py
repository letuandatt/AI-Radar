"""Bootstrap logic for the Knowledge Repository.

This module bridges the application settings and the RepositoryInitializer,
keeping database-specific configuration details out of the application core.
"""

from app.config.settings import Settings, get_settings
from app.core.logger import get_logger
from app.services.analysis.content_analyzer import ContentAnalyzer
from app.services.analysis.cross_source_analyzer import CrossSourceAnalyzer
from app.services.analysis.service import AnalysisService
from app.services.analysis.pattern_discoverer import PatternDiscoverer
from app.services.repository.config import RepositoryConfig
from app.services.repository.initializer import RepositoryInitializer

logger = get_logger(__name__)


def build_repository_config(settings: Settings) -> RepositoryConfig:
    """Build the RepositoryConfig fully from application settings (E2/E3).

    Storage paths and embedding provider are settings-driven so deployment
    never depends on paths inside the source tree.

    Args:
        settings: Application settings.

    Returns:
        RepositoryConfig for RepositoryInitializer.
    """
    return RepositoryConfig(
        sqlite_path=settings.sqlite_path,
        qdrant_url=settings.qdrant_url,
        qdrant_collection="knowledge_objects",
        bm25_index_path=settings.bm25_index_path,
        embedding_provider_type=settings.embedding_provider,
        ollama_base_url=settings.ollama_base_url,
        cohere_api_key=settings.cohere_api_key or None,
    )


def initialize_knowledge_repository(settings: Settings) -> RepositoryInitializer:
    """Build and initialize the Knowledge Repository from application settings.

    Args:
        settings: Application settings.

    Returns:
        Initialized RepositoryInitializer instance.
    """
    config = build_repository_config(settings)

    initializer = RepositoryInitializer(config)

    # Fail fast if critical components are unavailable
    state = initializer.initialize()

    logger.info(
        "Knowledge Repository initialized: sqlite=%d, vector=%d, bm25=%d, healthy=%s",
        state.sqlite_count,
        state.qdrant_count,
        state.bm25_count,
        state.is_healthy,
    )

    return initializer


def create_application_services(initializer: "RepositoryInitializer"):
    """Create ApplicationService and all its dependencies from an initializer.

    This factory function keeps database-specific property access
    (e.g., initializer.qdrant_store) out of the application core module.

    Args:
        initializer: Initialized RepositoryInitializer.

    Returns:
        Fully wired ApplicationService instance.
    """
    from app.services.app_service import ApplicationService
    from app.services.repository.access_service import RepositoryAccessService
    from app.services.repository.lifecycle_service import RepositoryLifecycleService

    access_service = RepositoryAccessService(
        sqlite_store=initializer.sqlite_store,
    )

    lifecycle_service = RepositoryLifecycleService(
        config=initializer.config,
        sqlite_store=initializer.sqlite_store,
        qdrant_store=initializer.qdrant_store,
        bm25_index=initializer.bm25_index,
    )
    lifecycle_service.start()

    return ApplicationService(
        initializer=initializer,
        access_service=access_service,
        lifecycle_service=lifecycle_service,
    )


def create_retrieval_service(initializer: "RepositoryInitializer"):
    """Create RetrievalService and all its dependencies from an initializer.

    This factory function keeps database-specific wiring
    (QdrantVectorStore, BM25Index, EmbeddingProvider) out of
    the application core module.

    Args:
        initializer: Initialized RepositoryInitializer.

    Returns:
        Fully wired RetrievalService instance.
    """
    from app.services.retrieval.fusion_retriever import FusionRetriever
    from app.services.retrieval.metadata_filter import MetadataFilterEngine
    from app.services.retrieval.retrieval_service import RetrievalService
    from app.services.retrieval.vector_search import VectorSearchService

    filter_engine = MetadataFilterEngine()

    vector_search = VectorSearchService(
        qdrant_store=initializer.qdrant_store,
        embedding_provider=initializer.embedding_provider,
        filter_engine=filter_engine,
    )

    fusion_retriever = FusionRetriever(
        vector_search=vector_search,
        bm25_index=initializer.bm25_index,
    )

    return RetrievalService(
        vector_search=vector_search,
        fusion_retriever=fusion_retriever,
        bm25_index=initializer.bm25_index,
        sqlite_store=initializer.sqlite_store,
        filter_engine=filter_engine,
    )


def create_llm_chain(settings: Settings):
    """Create the application-wide LLM provider chain from settings.

    ONE chain is shared by analysis and extraction so both workloads share
    one budget, one rate limiter and one fallback policy (provider order,
    model names, budget and alert threshold all come from Settings).

    Args:
        settings: Application settings.

    Returns:
        LLMProviderChain configured from settings.
    """
    from app.integrations.llm.factory import LLMProviderFactory

    return LLMProviderFactory.create(
        primary_provider=settings.llm_primary_provider,
        fallback_providers=settings.llm_fallback_providers or None,
        ollama_model=settings.ollama_model,
        groq_model=settings.groq_model,
        groq_api_key=settings.groq_api_key,
        daily_budget_usd=settings.llm_daily_budget_usd,
        alert_percent=settings.llm_alert_percent,
        rate_limit_rpm=settings.llm_rate_limit_rpm,
        rate_limit_wait_timeout=settings.llm_rate_limit_wait_timeout,
        daily_token_limit=settings.llm_daily_token_limit,
        daily_request_limit=settings.llm_daily_request_limit,
    )


def create_analysis_service(
    initializer: RepositoryInitializer, llm_chain, *, max_groups: int = 20
) -> AnalysisService:
    """Create the analysis component with shared repository and provider dependencies.

    Args:
        initializer: Initialized repository with all stores ready.
        llm_chain: Shared LLM provider chain (see create_llm_chain) —
            injected so analysis and extraction count against one budget.
        max_groups: Maximum number of cross-source groups returned per call.

    Returns:
        AnalysisService preserving analyze()/analyze_batch() for existing callers.
    """
    from app.prompts.loader import PromptLoader
    from app.services.repository.access_service import RepositoryAccessService

    settings = get_settings()

    access_service = RepositoryAccessService(initializer.sqlite_store)

    prompt_loader = PromptLoader()

    content = ContentAnalyzer(
        access_service=access_service,
        llm_provider=llm_chain,
        prompt_loader=prompt_loader,
        max_concurrent=settings.llm_max_concurrent,
    )
    cross_source = CrossSourceAnalyzer(access_service, llm_chain, max_groups=max_groups)
    patterns = PatternDiscoverer(access_service, llm_chain, prompt_loader)
    return AnalysisService(content=content, cross_source=cross_source, patterns=patterns)
