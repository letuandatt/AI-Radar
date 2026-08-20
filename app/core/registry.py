"""Component Registry for dependency management.

This module provides a centralized registry for managing application components.
It handles registration, lifecycle management (initialization and shutdown),
and prioritized access to components.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.core.logger import get_logger

logger = get_logger(__name__)


class ComponentNotFoundError(KeyError):
    """Raised when a requested component is not found in the registry."""


class ComponentNotInitializedError(RuntimeError):
    """Raised when accessing a component that has not been initialized yet."""


@dataclass
class _ComponentEntry:
    """Internal representation of a registered component."""

    name: str
    init_func: Callable[[], Any]
    shutdown_func: Callable[[Any], None]
    priority: int
    instance: Any = None
    is_initialized: bool = False


class ComponentRegistry:
    """Centralized registry for application components.

    This registry manages the registration, initialization, and shutdown
    of application components. It ensures that components are started
    in priority order and stopped in reverse priority order.

    Lifecycle:
    1. Register components with their initialization and shutdown functions.
    2. Start all components in priority order.
    3. Access components via get_component().
    4. Shutdown all components in reverse priority order.
    """

    def __init__(self) -> None:
        """Initialize an empty component registry."""
        self._entries: dict[str, _ComponentEntry] = {}

    def register(
        self,
        name: str,
        init_func: Callable[[], Any],
        shutdown_func: Callable[[Any], None],
        priority: int,
    ) -> None:
        """Register a component with the given name and lifecycle functions.

        Args:
            name: Unique identifier for the component.
            init_func: Function to initialize the component. Must return the component instance.
            shutdown_func: Function to shutdown the component. Receives the instance as argument.
            priority: Integer priority for startup order (lower starts first).

        Raises:
            ValueError: If a component with the same name is already registered.
        """
        if name in self._entries:
            raise ValueError(f"Component '{name}' is already registered.")

        self._entries[name] = _ComponentEntry(
            name=name,
            init_func=init_func,
            shutdown_func=shutdown_func,
            priority=priority,
        )
        logger.debug("Component '%s' registered with priority %d", name, priority)

    def start_all(self) -> None:
        """Initialize all registered components in priority order.

        Components are initialized from lowest priority value to highest.
        If any component fails to initialize, all previously initialized
        components will be shut down (rollback) before raising the exception.

        Raises:
            Exception: Re-raises the exception from the failed component initialization.
        """
        sorted_entries = sorted(self._entries.values(), key=lambda e: e.priority)
        initialized_entries: list[_ComponentEntry] = []

        # Khai báo biến theo dõi an toàn
        failed_entry: _ComponentEntry | None = None

        try:
            for entry in sorted_entries:
                failed_entry = entry  # Gán trước khi thực thi init
                logger.info("Initializing component '%s'", entry.name)
                instance = entry.init_func()
                entry.instance = instance
                entry.is_initialized = True
                initialized_entries.append(entry)
                logger.info("Component '%s' initialized successfully", entry.name)
        except Exception:
            # Sử dụng biến an toàn, kiểm tra None trước khi log
            if failed_entry is not None:
                logger.error(
                    "Failed to initialize component '%s'. Rolling back initialized components.",
                    failed_entry.name,
                )

            # Rollback in reverse order
            for initialized_entry in reversed(initialized_entries):
                try:
                    logger.info("Rolling back component '%s'", initialized_entry.name)
                    initialized_entry.shutdown_func(initialized_entry.instance)
                    initialized_entry.is_initialized = False
                except Exception as rollback_error:
                    logger.error(
                        "Failed to rollback component '%s': %s",
                        initialized_entry.name,
                        rollback_error,
                    )
            raise

    def shutdown_all(self) -> None:
        """Shutdown all initialized components in reverse priority order.

        Components are shutdown from highest priority value to lowest.
        Errors during shutdown are logged but do not stop the process,
        ensuring all components have a chance to release resources.
        """
        sorted_entries = sorted(self._entries.values(), key=lambda e: e.priority, reverse=True)

        for entry in sorted_entries:
            if entry.is_initialized:
                logger.info("Shutting down component '%s'", entry.name)
                try:
                    entry.shutdown_func(entry.instance)
                except Exception as error:
                    logger.error("Error shutting down component '%s': %s", entry.name, error)
                finally:
                    entry.is_initialized = False
                    entry.instance = None

    def get_component(self, name: str) -> Any:
        """Retrieve an initialized component by name.

        Args:
            name: The name of the component to retrieve.

        Returns:
            The initialized component instance.

        Raises:
            ComponentNotFoundError: If no component with the given name exists.
            ComponentNotInitializedError: If the component exists but has not been initialized.
        """
        entry = self._entries.get(name)
        if entry is None:
            raise ComponentNotFoundError(f"Component '{name}' not found in registry.")

        if not entry.is_initialized:
            raise ComponentNotInitializedError(
                f"Component '{name}' is registered but not initialized. Call start_all() first."
            )

        return entry.instance

    def has_component(self, name: str) -> bool:
        """Check if a component is registered.

        Args:
            name: The name of the component to check.

        Returns:
            True if the component is registered, False otherwise.
        """
        return name in self._entries
