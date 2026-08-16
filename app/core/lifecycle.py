"""Application lifecycle state model.

This module defines the valid application states and transitions used by the
application startup and shutdown flow.
"""

from enum import Enum


class ApplicationState(str, Enum):
    """States an application instance can occupy during its lifetime."""

    CREATED = "created"
    INITIALIZING = "initializing"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"


class LifecycleTransitionError(RuntimeError):
    """Raised when an operation is invalid for the current lifecycle state."""


class ApplicationLifecycle:
    """Owns lifecycle state and enforces its permitted transitions.

    Valid transitions:
    - ``Created -> Initializing`` via :meth:`begin_initialization`
    - ``Initializing -> Running`` via :meth:`mark_running`
    - ``Initializing -> Stopped`` via :meth:`fail_initialization`
    - ``Running -> Stopping`` via :meth:`begin_stopping`
    - ``Stopping -> Stopped`` via :meth:`mark_stopped`
    """

    def __init__(self) -> None:
        self._state = ApplicationState.CREATED

    @property
    def state(self) -> ApplicationState:
        """Return the current application lifecycle state."""
        return self._state

    def begin_initialization(self) -> None:
        self._transition(ApplicationState.CREATED, ApplicationState.INITIALIZING)

    def mark_running(self) -> None:
        self._transition(ApplicationState.INITIALIZING, ApplicationState.RUNNING)

    def fail_initialization(self) -> None:
        self._transition(ApplicationState.INITIALIZING, ApplicationState.STOPPED)

    def begin_stopping(self) -> None:
        self._transition(ApplicationState.RUNNING, ApplicationState.STOPPING)

    def mark_stopped(self) -> None:
        self._transition(ApplicationState.STOPPING, ApplicationState.STOPPED)

    def _transition(
        self,
        expected_state: ApplicationState,
        next_state: ApplicationState,
    ) -> None:
        if self._state is not expected_state:
            raise LifecycleTransitionError(
                f"Cannot transition from {self._state.value} to {next_state.value}; "
                f"expected {expected_state.value}."
            )

        self._state = next_state
