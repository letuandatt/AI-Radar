"""Scheduler foundation and lifecycle state."""

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any

from app.core.exceptions import DuplicateJobError
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


@dataclass(frozen=True)
class Job:
    """Definition of a registered scheduler job."""

    job_id: str
    func: Callable[..., Any]


class Scheduler:
    """Owns scheduler initialization state.

    Job registration and execution are intentionally outside this scope.
    """

    def __init__(self) -> None:
        self._state = SchedulerState.CREATED
        self._jobs: dict[str, Job] = {}

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

    def register_job(self, job: Job) -> None:
        """Register a job with the scheduler."""
        self._ensure_ready()

        if job.job_id in self._jobs:
            raise DuplicateJobError(f"Job '{job.job_id}' is already registered.")

        self._jobs[job.job_id] = job

        logger.info("Job registered: %s", job.job_id)

    def get_job(self, job_id: str) -> Job:
        """Return a registered job by its identifier."""
        self._ensure_ready()

        return self._jobs[job_id]

    def has_job(self, job_id: str) -> bool:
        """Return whether a job is registered."""
        self._ensure_ready()

        return job_id in self._jobs

    def _ensure_ready(self) -> None:
        """Ensure the scheduler is ready for scheduler operations."""
        if self._state is not SchedulerState.READY:
            raise SchedulerStateError(
                f"Scheduler must be ready for this operation; current state is {self._state.value}."
            )
