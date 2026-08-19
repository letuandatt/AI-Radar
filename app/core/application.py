from ..config.settings import get_settings
from ..core.logger import initialize_logging, shutdown_logging
from ..core.scheduler import Scheduler
from ..storage.qdrant_client import QdrantConnection
from .lifecycle import ApplicationLifecycle

_scheduler: Scheduler | None = None
_database: QdrantConnection | None = None


def start_application(lifecycle: ApplicationLifecycle) -> None:
    """Run bootstrap and advance the lifecycle to ``Running`` on success."""
    global _scheduler, _database

    lifecycle.begin_initialization()

    try:
        initialize_application()
        _scheduler = initialize_core()
        _database = initialize_storage()
    except Exception:
        lifecycle.fail_initialization()
        raise

    lifecycle.mark_running()


def shutdown_application(lifecycle: ApplicationLifecycle) -> None:
    """Stop initialized components and advance the lifecycle to ``Stopped``.

    Components are released in reverse startup order. The nested ``finally``
    blocks ensure later cleanup still runs when an earlier shutdown step fails.
    """
    lifecycle.begin_stopping()

    try:
        shutdown_core()
        shutdown_storage()
    finally:
        try:
            shutdown_logging()
        finally:
            lifecycle.mark_stopped()


def run_application() -> None:
    """Run application work after startup.

    The scheduler will own the runtime workload in a later PBI. This hook
    keeps the lifecycle execution flow complete without introducing scheduler
    behavior before that dependency exists.
    """
    pass


def initialize_application() -> None:
    load_configuration()
    initialize_logging()


def load_configuration():
    return get_settings


def initialize_core() -> Scheduler:
    scheduler = Scheduler()
    scheduler.initialize()

    return scheduler


def shutdown_core() -> None:
    """Stop initialized application-level core components."""
    global _scheduler

    if _scheduler is not None:
        _scheduler.stop()
        _scheduler = None


def initialize_storage() -> QdrantConnection:
    """Initialize the database connection using centralized configuration."""
    settings = get_settings()
    database = QdrantConnection(settings)
    database.initialize()
    return database


def shutdown_storage() -> None:
    """Close the database connection and release resources."""
    global _database

    if _database is not None:
        _database.close()
        _database = None
