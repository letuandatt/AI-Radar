"""Core infrastructure module.

This module provides foundational utilities and infrastructure for the AI-Radar application.
It includes logging, exception handling, application lifecycle management, and component registry.

Shared Access Points (Internal to Core):
- `get_logger`: Obtain a named logger instance.
- `report_application_error`: Centralized error reporting.
- `ApplicationLifecycle`: Manage application startup and shutdown states.
- `ComponentRegistry`: Manage component initialization and teardown.
"""

from .exceptions import ApplicationError, report_application_error
from .lifecycle import ApplicationLifecycle, ApplicationState
from .logger import get_logger, initialize_logging, shutdown_logging
from .registry import (
    ComponentNotFoundError,
    ComponentNotInitializedError,
    ComponentRegistry,
)

__all__ = [
    "ApplicationError",
    "report_application_error",
    "ApplicationLifecycle",
    "ApplicationState",
    "get_logger",
    "initialize_logging",
    "shutdown_logging",
    "ComponentNotFoundError",
    "ComponentNotInitializedError",
    "ComponentRegistry",
]
