import logging

from app.config.constants import DEFAULT_LOG_LEVEL


def initialize_logging() -> None:
    """Initialize application-wide logging configuration."""
    root_logger = logging.getLogger()

    if root_logger.handlers:
        root_logger.setLevel(DEFAULT_LOG_LEVEL)
        return

    handler = logging.StreamHandler()
    handler.setLevel(DEFAULT_LOG_LEVEL)

    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    handler.setFormatter(formatter)

    root_logger.setLevel(DEFAULT_LOG_LEVEL)
    root_logger.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    """Return a logger for the given module/component."""
    return logging.getLogger(name)


def shutdown_logging() -> None:
    """Shutdown application-wide logging handlers."""
    root_logger = logging.getLogger()

    for handler in root_logger.handlers[:]:
        handler.close()
        root_logger.removeHandler(handler)
