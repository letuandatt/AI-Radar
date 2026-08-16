from .core.application import run_application, shutdown_application, start_application
from .core.lifecycle import ApplicationLifecycle, ApplicationState


def main() -> ApplicationLifecycle:
    lifecycle = ApplicationLifecycle()

    try:
        start_application(lifecycle)
        run_application()
    except Exception as error:
        print(f"Startup failed: {error}")
        raise
    finally:
        if lifecycle.state is ApplicationState.RUNNING:
            shutdown_application(lifecycle)

    return lifecycle


if __name__ == "__main__":
    main()
