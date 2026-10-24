"""Start the local application runtime.

From the repository root:
    python -m app.main
    python app/main.py

IDE run configurations should use the repository root as the working directory
so relative settings, configuration files and storage paths resolve consistently.
"""

import sys
from pathlib import Path

# Direct file execution has no package context and puts app/ on sys.path.
# Add its parent before importing app; module execution already has that context.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.application import (  # noqa: E402
    run_application,
    shutdown_application,
    start_application,
)
from app.core.exceptions import handle_application_exception  # noqa: E402
from app.core.lifecycle import ApplicationLifecycle, ApplicationState  # noqa: E402
from app.core.logger import get_logger, initialize_logging  # noqa: E402

logger = get_logger(__name__)


def main() -> ApplicationLifecycle:
    initialize_logging()
    lifecycle = ApplicationLifecycle()

    logger.info("Application startup")

    try:
        start_application(lifecycle)
        run_application()
    except Exception as error:
        handle_application_exception(
            error,
            context={
                "operation": "application_runtime",
                "lifecycle_state": lifecycle.state.value,
            },
        )
    finally:
        if lifecycle.state is ApplicationState.RUNNING:
            shutdown_application(lifecycle)
            logger.info("Application shutdown")

    return lifecycle


if __name__ == "__main__":
    main()
