from ..config.settings import settings
from .lifecycle import ApplicationLifecycle


def start_application(lifecycle: ApplicationLifecycle) -> None:
    """Run bootstrap and advance the lifecycle to ``Running`` on success."""
    lifecycle.begin_initialization()

    try:
        initialize_application()
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


def initialize_application():
    config = load_configuration()

    validate_configuration(config)

    initialize_logging(config)

    initialize_core(config)


def load_configuration():
    return settings


def validate_configuration(config):
    print("config - validated")


def initialize_logging(config):
    print("config - logging initialized")


def initialize_core(config):
    print("config - core initialized")


def shutdown_core():
    """Release application-level core components.

    This is an extension point until core components gain concrete resources.
    """


def shutdown_logging():
    """Release logging resources after dependent components have stopped."""
