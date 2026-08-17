from .core.application import run_application, shutdown_application, start_application
from .core.exceptions import handle_application_exception
from .core.lifecycle import ApplicationLifecycle, ApplicationState
from .core.logger import get_logger, initialize_logging

logger = get_logger(__name__)


def main() -> ApplicationLifecycle:
    initialize_logging()

    lifecycle = ApplicationLifecycle()

    logger.info("Application startup")

    try:
        start_application(lifecycle)
        run_application()
    except Exception as error:
        handle_application_exception(error)
    finally:
        if lifecycle.state is ApplicationState.RUNNING:
            shutdown_application(lifecycle)
            logger.info("Application shutdown")

    return lifecycle


if __name__ == "__main__":
    main()
