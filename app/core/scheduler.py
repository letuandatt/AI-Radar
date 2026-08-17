"""Scheduler foundation and lifecycle state."""

from enum import Enum

from app.core.logger import get_logger

logger = get_logger(__name__)


class SchedulerState(str, Enum):
    """States a scheduler instance can occupy."""

    CREATED = "created"
    INITIALIZING = "initializing"
    READY = "ready"
    STOPPED = "stopped"


class SchedulerStateError(RuntimeError):
    """Raised when a scheduler operation is invalid for its current state."""


class Scheduler:
    """Owns scheduler initialization state.

    Job registration and execution are intentionally outside this scope.
    """

    def __init__(self) -> None:
        self._state = SchedulerState.CREATED

    @property
    def state(self) -> SchedulerState:
        """Return the current scheduler state."""
        return self._state

    @property
    def is_ready(self) -> bool:
        """Return whether the scheduler is ready for later scheduler operations."""
        return self._state is SchedulerState.READY

    def initialize(self) -> None:
        """Initialize the scheduler and make it ready."""
        if self._state is not SchedulerState.CREATED:
            raise SchedulerStateError(
                f"Cannot initialize scheduler from {self._state.value} state."
            )

        self._state = SchedulerState.INITIALIZING

        logger.info("Scheduler initialization started")

        self._state = SchedulerState.READY

        logger.info("Scheduler is ready")

    def stop(self) -> None:
        """Stop the scheduler and release scheduler resources."""
        if self._state is SchedulerState.STOPPED:
            return

        if self._state is not SchedulerState.READY:
            raise SchedulerStateError(f"Cannot stop scheduler from {self._state.value} state.")

        logger.info("Scheduler stopping")

        self._state = SchedulerState.STOPPED

        logger.info("Scheduler stopped")
