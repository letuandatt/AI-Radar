"""Application lifecycle management.

This module orchestrates the startup and shutdown of the AI-Radar application.
It uses a ComponentRegistry to manage the initialization and teardown of
core components in a prioritized and safe manner.
"""

from ..config.settings import get_settings
from ..core.logger import initialize_logging, shutdown_logging
from ..core.registry import ComponentRegistry
from ..core.scheduler import Scheduler
from ..storage.base import get_storage, initialize_storage, shutdown_storage
from .lifecycle import ApplicationLifecycle

_registry: ComponentRegistry | None = None


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


def start_application(lifecycle: ApplicationLifecycle) -> None:
    """Run bootstrap and advance the lifecycle to ``Running`` on success."""
    global _registry

    lifecycle.begin_initialization()

    try:
        _registry = ComponentRegistry()

        # Register components with priority
        _registry.register("logging", _init_logging, _shutdown_logging, priority=10)
        _registry.register("scheduler", _init_scheduler, _shutdown_scheduler, priority=20)
        _registry.register("storage", _init_storage, _shutdown_storage, priority=30)

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
