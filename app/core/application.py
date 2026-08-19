from ..config.settings import get_settings
from ..core.logger import get_logger, initialize_logging, shutdown_logging
from ..core.scheduler import Scheduler
from ..storage.base import initialize_storage, shutdown_storage
from .lifecycle import ApplicationLifecycle

_scheduler: Scheduler | None = None
logger = get_logger(__name__)


def start_application(lifecycle: ApplicationLifecycle) -> None:
    """Run bootstrap and advance the lifecycle to ``Running`` on success."""
    global _scheduler

    lifecycle.begin_initialization()

    try:
        initialize_application()
        _scheduler = initialize_core()

        initialize_storage(get_settings())
    except Exception:
        lifecycle.fail_initialization()
        raise

    lifecycle.mark_running()


def shutdown_application(lifecycle: ApplicationLifecycle) -> None:
    """Stop initialized components and advance the lifecycle to ``Stopped``."""
    lifecycle.begin_stopping()

    # Tách riêng try-except cho từng component để đảm bảo component sau
    # vẫn được shutdown ngay cả khi component trước đó gặp lỗi.
    try:
        shutdown_core()
    except Exception as error:
        logger.error("Error during core shutdown: %s", error)

    try:
        shutdown_storage()
    except Exception as error:
        logger.error("Error during storage shutdown: %s", error)
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
