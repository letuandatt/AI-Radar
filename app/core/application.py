"""Application lifecycle management.

This module orchestrates the startup and shutdown of the AI-Radar application.
It uses a ComponentRegistry to manage the initialization and teardown of
core components in a prioritized and safe manner.
"""

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
from ..services.repository import (
    create_application_services,
    initialize_knowledge_repository,
)
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
    """Initialize the scheduler."""
    scheduler = Scheduler()
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


def _init_app_service():
    """Initialize ApplicationService facade.

    Uses factory from bootstrap layer to avoid accessing
    database-specific properties from application core.
    """
    assert _registry is not None, "ComponentRegistry must be initialized"
    initializer = _registry.get_component("repository")

    return create_application_services(initializer)


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

    # Create pipeline with all registries
    pipeline = DefaultAcquisitionPipeline(
        rss_registry=get_source_registry(),
        github_registry=get_github_registry(),
        hf_registry=get_hf_registry(),
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
    job = Job(
        job_id="acquisition_pipeline",
        func=pipeline.run,
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
        _registry.register("storage", _init_storage, _shutdown_storage, priority=30)
        _registry.register(
            "app_service",
            _init_app_service,
            _shutdown_app_service,
            priority=35,
        )
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


def run_application() -> None:
    """Run application work after startup."""
    pass


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
