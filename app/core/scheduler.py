"""Scheduler foundation and lifecycle state."""

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, time
from enum import Enum
from pathlib import Path
from typing import Any

from app.core.exceptions import DuplicateJobError, handle_application_exception
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
    schedule: time


class Scheduler:
    """Owns scheduler initialization state and daily due-job tracking.

    Due-job logic (A2): ``get_due_jobs`` returns jobs whose schedule time has
    been reached and that have not run yet today; ``mark_run`` records the
    run. Last-run dates are persisted to ``state_file`` so a process restart
    on the same day does not re-run a daily job.

    Args:
        state_file: Optional JSON file persisting per-job last-run dates.
            ``None`` keeps the guard in memory only (unit tests).
    """

    def __init__(self, state_file: Path | None = None) -> None:
        self._state = SchedulerState.CREATED
        self._jobs: dict[str, Job] = {}
        self._state_file = state_file
        self._last_run_dates: dict[str, str] = self._load_last_run_dates()

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

    def execute_scheduled_job(
        self,
        job_id: str,
        current_time: time,
    ) -> Any:
        """Execute a registered job when its scheduled time is reached.

        This is the execution API for EXTERNAL scheduling systems (E1/D2):
        a cron runner or dedicated entrypoint calls it per job. The
        in-process loop (``run_application``) does not use it — that loop
        goes through ``get_due_jobs`` + ``run_scheduled_cycle`` in
        application.py, which isolate per-job failures instead of
        propagating them.
        """
        self._ensure_ready()

        job = self.get_job(job_id)

        if current_time < job.schedule:
            return None

        logger.info("Executing scheduled job: %s", job.job_id)

        try:
            result = job.func()
        except Exception as error:
            handle_application_exception(
                error,
                context={
                    "operation": "job_execution",
                    "job_id": job.job_id,
                },
            )

        logger.info("Job execution completed: %s", job.job_id)

        return result

    def get_due_jobs(self, now: datetime) -> list[Job]:
        """Return jobs due at ``now``: schedule reached and not run today.

        Args:
            now: Current wall-clock datetime (injected for testability).

        Returns:
            Jobs to run now, in registration order.
        """
        self._ensure_ready()

        today = now.date().isoformat()
        return [
            job
            for job in self._jobs.values()
            if self._last_run_dates.get(job.job_id) != today and now.time() >= job.schedule
        ]

    def mark_run(self, job_id: str, now: datetime) -> None:
        """Record that ``job_id`` started at ``now`` and persist the date.

        Args:
            job_id: Identifier of the job that started.
            now: Current wall-clock datetime (injected for testability).

        Raises:
            KeyError: If the job is not registered.
        """
        self._ensure_ready()

        if job_id not in self._jobs:
            raise KeyError(f"Job '{job_id}' is not registered.")

        self._last_run_dates[job_id] = now.date().isoformat()
        self._save_last_run_dates()

    def get_last_run_date(self, job_id: str) -> str | None:
        """Return the ISO date the job last started, or None."""
        return self._last_run_dates.get(job_id)

    def _load_last_run_dates(self) -> dict[str, str]:
        """Load persisted last-run dates; corrupt files degrade to empty."""
        if self._state_file is None or not self._state_file.exists():
            return {}
        try:
            data = json.loads(self._state_file.read_text(encoding="utf-8"))
            return {str(key): str(value) for key, value in data.items()}
        except (OSError, ValueError) as e:
            logger.warning("Could not load scheduler state %s: %s", self._state_file, e)
            return {}

    def _save_last_run_dates(self) -> None:
        """Persist last-run dates; failures are logged, never fatal."""
        if self._state_file is None:
            return
        try:
            self._state_file.parent.mkdir(parents=True, exist_ok=True)
            self._state_file.write_text(json.dumps(self._last_run_dates), encoding="utf-8")
        except OSError as e:
            logger.error("Could not save scheduler state %s: %s", self._state_file, e)
