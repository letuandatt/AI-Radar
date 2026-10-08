"""Application lifecycle management.

This module orchestrates the startup and shutdown of the AI-Radar application.
It uses a ComponentRegistry to manage the initialization and teardown of
core components in a prioritized and safe manner.
"""

import time
from datetime import datetime

from ..config.settings import get_settings
from ..core.logger import get_logger, initialize_logging, shutdown_logging
from ..core.registry import ComponentRegistry
from ..core.scheduler import Job, Scheduler
from ..fetchers.registry import (
    get_github_registry,
    get_hf_registry,
    get_source_registry,
    initialize_github_registry,
    initialize_hf_registry,
    initialize_source_registry,
)
from ..pipelines.acquisition import DefaultAcquisitionPipeline
from ..pipelines.knowledge_update import build_processing_pipeline, run_knowledge_update
from ..pipelines.processing import ProcessingPipeline
from ..services.repository import (
    create_application_services,
    create_retrieval_service,
    initialize_knowledge_repository,
)
from ..services.repository.bootstrap import create_analysis_service, create_llm_chain
from ..storage.base import get_storage, initialize_storage, shutdown_storage
from .lifecycle import ApplicationLifecycle

_registry: ComponentRegistry | None = None
logger = get_logger(__name__)


def _init_logging() -> str:
    """Initialize the logging system."""
    get_settings()  # Trigger configuration loading and validation
    initialize_logging()
    return "logging"


def _shutdown_logging(instance: str) -> None:
    """Shutdown the logging system."""
    shutdown_logging()


def _init_scheduler() -> Scheduler:
    """Initialize the scheduler with persisted last-run-date state."""
    scheduler = Scheduler(state_file=get_settings().scheduler_state_path)
    scheduler.initialize()
    return scheduler


def _shutdown_scheduler(scheduler: Scheduler) -> None:
    """Shutdown the scheduler."""
    scheduler.stop()


def _init_storage() -> object:
    """Initialize the storage layer."""
    initialize_storage(get_settings())
    return get_storage()


def _shutdown_storage(instance: object) -> None:
    """Shutdown the storage layer."""
    shutdown_storage()


def _init_repository():
    """Initialize the Knowledge Repository stack.

    Creates SQLite store, vector store, BM25 index, and embedding provider.
    Fails fast if critical components are unavailable.

    Returns:
        Initialized RepositoryInitializer instance.
    """
    return initialize_knowledge_repository(get_settings())


def _shutdown_repository(initializer) -> None:
    """Gracefully shutdown the Knowledge Repository."""
    initializer.shutdown()


def _init_retrieval():
    """Initialize the Retrieval Service (S18).

    Creates MetadataFilterEngine, VectorSearchService, FusionRetriever,
    and RetrievalService from repository components.
    Uses factory from bootstrap layer to avoid database-specific imports.

    Returns:
        Fully wired RetrievalService instance.
    """
    assert _registry is not None, "ComponentRegistry must be initialized"
    initializer = _registry.get_component("repository")

    return create_retrieval_service(initializer)


def _shutdown_retrieval(retrieval_service) -> None:
    """Shutdown the Retrieval Service (no-op, stateless)."""
    logger.debug("Retrieval service shutdown (no-op)")


def _init_app_service():
    """Initialize ApplicationService facade.

    Uses factory from bootstrap layer to avoid accessing
    database-specific properties from application core.
    """
    assert _registry is not None, "ComponentRegistry must be initialized"
    initializer = _registry.get_component("repository")

    app_service = create_application_services(initializer)

    retrieval_service = _registry.get_component("retrieval")
    app_service.set_retrieval_service(retrieval_service)

    return app_service


def _shutdown_app_service(app_service) -> None:
    """Gracefully shutdown ApplicationService and its dependencies."""
    try:
        app_service.get_lifecycle().stop()
    except Exception as e:
        logger.error("Error shutting down ApplicationService: %s", e)


def _init_acquisition() -> DefaultAcquisitionPipeline:
    """Initialize acquisition pipeline and register it as a scheduled job.

    This function:
    1. Initializes all source registries (RSS, GitHub, HuggingFace).
    2. Creates a DefaultAcquisitionPipeline instance.
    3. Registers the pipeline as a scheduled job in the Scheduler.
    4. Optionally runs the pipeline immediately on startup.

    Priority ensures this runs AFTER scheduler and storage are ready.
    """
    settings = get_settings()

    # Initialize source registries first
    initialize_source_registry(settings)
    initialize_github_registry(settings)
    initialize_hf_registry(settings)
    logger.info("All source registries initialized")

    # Get the initialized scheduler component
    assert _registry is not None, "ComponentRegistry must be initialized"
    scheduler: Scheduler = _registry.get_component("scheduler")

    # Get the processing pipeline (A1: acquisition forwards articles to it)
    processing_pipeline: ProcessingPipeline | None = None
    if settings.knowledge_update_enabled:
        try:
            processing_pipeline = _registry.get_component("processing")
        except Exception as e:
            logger.warning("Processing pipeline unavailable; job will be acquisition-only: %s", e)

    # Create pipeline with all registries
    pipeline = DefaultAcquisitionPipeline(
        rss_registry=get_source_registry(),
        github_registry=get_github_registry(),
        hf_registry=get_hf_registry(),
        settings=settings,
    )

    # Inject ApplicationService if available
    try:
        app_service = _registry.get_component("app_service")
        pipeline.set_app_service(app_service)
        logger.info("ApplicationService injected into acquisition pipeline")
    except Exception as e:
        logger.warning(
            "Could not inject ApplicationService into acquisition pipeline: %s. "
            "Pipeline will use fallback JSON storage.",
            e,
        )

    # Register as a scheduled job
    def knowledge_update_job() -> None:
        """Run acquisition, then forward its articles into processing (A1)."""
        acquisition_result = pipeline.run()
        if processing_pipeline is None or not acquisition_result.articles:
            return
        try:
            processing_result = run_knowledge_update(acquisition_result, processing_pipeline)
        except Exception as error:
            logger.error("Knowledge update failed: %s", error, exc_info=True)
            return
        if processing_result is None:
            return
        logger.info(
            "Knowledge update completed: created=%d, updated=%d, failed=%d",
            processing_result.objects_created,
            processing_result.objects_updated,
            processing_result.failed_objects,
        )

    job = Job(
        job_id="acquisition_pipeline",
        func=knowledge_update_job,
        schedule=settings.acquisition_schedule_time,
    )
    scheduler.register_job(job)
    logger.info(
        "Acquisition pipeline registered with schedule: %s",
        settings.acquisition_schedule_time.isoformat(),
    )

    # Run on startup if configured
    if settings.acquisition_run_on_startup:
        logger.info("Running acquisition pipeline on startup...")
        try:
            result = pipeline.run()
            logger.info(
                "Startup acquisition completed: %d/%d sources succeeded, "
                "%d articles in %.2f seconds",
                result.successful_sources,
                result.total_sources,
                result.total_articles,
                result.execution_time,
            )
        except Exception as error:
            logger.error("Startup acquisition failed: %s", error, exc_info=True)

    return pipeline


def _shutdown_acquisition(pipeline: DefaultAcquisitionPipeline) -> None:
    """Shutdown the acquisition pipeline (no-op, pipeline is stateless)."""
    logger.debug("Acquisition pipeline shutdown (no-op)")


def _init_llm_chain():
    """Create the shared LLM provider chain for ALL LLM workloads.

    One chain = one budget, one rate limiter, one fallback policy across
    analysis and extraction.

    Returns:
        LLMProviderChain built from settings.
    """
    return create_llm_chain(get_settings())


def _shutdown_llm_chain(llm_chain) -> None:
    """Shutdown the LLM chain (no-op, providers hold no resources)."""
    logger.debug("LLM provider chain shutdown (no-op)")


def _init_processing() -> ProcessingPipeline:
    """Initialize the Processing Pipeline wired to the knowledge repository (A1).

    Composes cleaning/normalization/extraction stages with the repository's
    SQLite knowledge store so processed articles are actually persisted.

    Returns:
        Fully wired ProcessingPipeline.
    """
    assert _registry is not None, "ComponentRegistry must be initialized"
    initializer = _registry.get_component("repository")
    llm_chain = _registry.get_component("llm_chain")
    return build_processing_pipeline(initializer, get_settings(), llm_chain)


def _shutdown_processing(pipeline: ProcessingPipeline) -> None:
    """Shutdown the processing pipeline (no-op, stages are stateless)."""
    logger.debug("Processing pipeline shutdown (no-op)")


def _init_analysis():
    """Initialize the content and cross-source analysis component."""
    initializer = _registry.get_component("repository")
    llm_chain = _registry.get_component("llm_chain")
    return create_analysis_service(initializer, llm_chain)


def _shutdown_analysis(analysis_service) -> None:
    """Shutdown the analysis component (no-op, stateless)."""
    logger.debug("Analysis service shutdown (no-op)")


def start_application(lifecycle: ApplicationLifecycle) -> None:
    """Run bootstrap and advance the lifecycle to ``Running`` on success."""
    global _registry

    lifecycle.begin_initialization()

    try:
        _registry = ComponentRegistry()

        # Register components with priority
        _registry.register("logging", _init_logging, _shutdown_logging, priority=10)
        _registry.register(
            "repository",
            _init_repository,
            _shutdown_repository,
            priority=15,
        )
        _registry.register("scheduler", _init_scheduler, _shutdown_scheduler, priority=20)
        _registry.register(
            "retrieval",
            _init_retrieval,
            _shutdown_retrieval,
            priority=25,
        )
        _registry.register("storage", _init_storage, _shutdown_storage, priority=30)
        _registry.register(
            "app_service",
            _init_app_service,
            _shutdown_app_service,
            priority=35,
        )
        _registry.register("llm_chain", _init_llm_chain, _shutdown_llm_chain, priority=36)
        _registry.register("analysis", _init_analysis, _shutdown_analysis, priority=37)
        _registry.register("processing", _init_processing, _shutdown_processing, priority=38)
        _registry.register("acquisition", _init_acquisition, _shutdown_acquisition, priority=40)

        # Start all components
        _registry.start_all()

    except Exception:
        lifecycle.fail_initialization()
        raise

    lifecycle.mark_running()


def shutdown_application(lifecycle: ApplicationLifecycle) -> None:
    """Stop initialized components and advance the lifecycle to ``Stopped``."""
    lifecycle.begin_stopping()

    try:
        if _registry is not None:
            _registry.shutdown_all()
    finally:
        lifecycle.mark_stopped()


def run_scheduled_cycle(scheduler: Scheduler, now: datetime) -> list[str]:
    """Run all jobs due at ``now``, isolating failures per job (A2).

    One failing job must never kill the caller: its exception is logged and
    the remaining due jobs still run. Jobs are marked run BEFORE executing so
    a crashing job does not loop-retry within the same day.

    Args:
        scheduler: Scheduler with registered jobs.
        now: Current wall-clock datetime (injected for testability).

    Returns:
        Ids of the jobs that were started.
    """
    executed: list[str] = []
    for job in scheduler.get_due_jobs(now):
        scheduler.mark_run(job.job_id, now)
        executed.append(job.job_id)
        try:
            job.func()
        except Exception as error:
            logger.error("Scheduled job %s failed: %s", job.job_id, error, exc_info=True)
    return executed


def run_application() -> None:
    """Run the application work loop until interrupted (A2).

    Every 60 seconds the loop checks the scheduler for due jobs and runs
    them (each at most once per day, guarded by the scheduler's persisted
    last-run dates). Production schedules the same jobs through external
    schedulers and dedicated entrypoints instead (E1/D2) — this loop is the
    local runtime.
    """
    assert _registry is not None, "Application registry is not initialized."
    scheduler: Scheduler = _registry.get_component("scheduler")
    logger.info("Application loop started (checking for due jobs every 60s)")
    try:
        while True:
            run_scheduled_cycle(scheduler, datetime.now())
            time.sleep(60)
    except KeyboardInterrupt:
        logger.info("Application loop stopped by user")


def get_component(name: str) -> object:
    """Retrieve a registered component by name.

    Args:
        name: The name of the component to retrieve.

    Returns:
        The initialized component instance.

    Raises:
        RuntimeError: If the application registry is not initialized.
    """
    if _registry is None:
        raise RuntimeError("Application registry is not initialized.")
    return _registry.get_component(name)
