"""Base Service foundation.

This module defines the application-level contract and base implementation
for all business services. It provides a unified lifecycle, state management,
centralized error handling, and shared logging.
"""

from abc import ABC, abstractmethod
from enum import Enum

from app.config.settings import Settings
from app.core.exceptions import report_application_error
from app.core.logger import get_logger


class ServiceState(str, Enum):
    """States a service instance can occupy during its lifecycle."""

    CREATED = "created"
    INITIALIZED = "initialized"
    RUNNING = "running"
    STOPPED = "stopped"
    SHUTDOWN = "shutdown"


class ServiceStateError(RuntimeError):
    """Raised when a service operation is invalid for its current state."""


class BaseService(ABC):
    """The application-level service base implementation.

    All business services must inherit from this class.
    It enforces a unified lifecycle, manages state transitions,
    and provides centralized error reporting and logging.

    Lifecycle:
    1. __init__: Receive dependencies (e.g., Settings).
    2. initialize(): Prepares resources. Calls _on_initialize() hook.
    3. start(): Executes core logic. Calls _on_start() hook.
    4. stop(): Halts operations. Calls _on_stop() hook.
    5. shutdown(): Releases resources. Calls _on_shutdown() hook.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._state = ServiceState.CREATED
        # Provide a logger named after the concrete subclass
        self._logger = get_logger(self.__class__.__name__)

    @property
    def state(self) -> ServiceState:
        """Return the current service state."""
        return self._state

    @property
    def is_running(self) -> bool:
        """Return whether the service is currently executing."""
        return self._state is ServiceState.RUNNING

    def initialize(self) -> None:
        """Initialize the service and transition to INITIALIZED state."""
        if self._state is not ServiceState.CREATED:
            raise ServiceStateError(f"Cannot initialize service from '{self._state.value}' state.")

        self._logger.info("Initializing service")
        self._on_initialize()
        self._state = ServiceState.INITIALIZED
        self._logger.info("Service initialized successfully")

    def _on_initialize(self) -> None:
        """Hook for subclasses to implement initialization logic."""
        pass

    @abstractmethod
    def _on_start(self) -> None:
        """Abstract hook for subclasses to implement core business logic."""
        ...

    def start(self) -> None:
        """Execute the service's core business logic."""
        if self._state is not ServiceState.INITIALIZED:
            raise ServiceStateError(
                f"Cannot start service from '{self._state.value}' state. Must be initialized first."
            )

        self._state = ServiceState.RUNNING
        self._logger.info("Service execution started")

        try:
            self._on_start()
        except Exception as error:
            # Centralized error reporting with service context
            report_application_error(
                error,
                context={
                    "operation": "service_execution",
                    "service_name": self.__class__.__name__,
                },
            )
            raise

    def stop(self) -> None:
        """Stop the service and transition to STOPPED state."""
        if self._state not in (ServiceState.INITIALIZED, ServiceState.RUNNING):
            raise ServiceStateError(f"Cannot stop service from '{self._state.value}' state.")

        self._logger.info("Stopping service")
        self._on_stop()
        self._state = ServiceState.STOPPED
        self._logger.info("Service stopped")

    def _on_stop(self) -> None:
        """Hook for subclasses to implement stop logic."""
        pass

    def shutdown(self) -> None:
        """Shutdown the service and release resources."""
        if self._state is ServiceState.SHUTDOWN:
            return  # Idempotent

        if self._state in (ServiceState.INITIALIZED, ServiceState.RUNNING):
            self.stop()

        self._state = ServiceState.SHUTDOWN
        self._logger.info("Shutting down service")
        self._on_shutdown()
        self._logger.info("Service shut down successfully")

    def _on_shutdown(self) -> None:
        """Hook for subclasses to implement shutdown logic."""
        pass
