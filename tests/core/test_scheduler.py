import logging
from datetime import time

import pytest

from app.core.exceptions import DuplicateJobError
from app.core.scheduler import Job, Scheduler, SchedulerState, SchedulerStateError


def test_scheduler_starts_in_created_state():
    scheduler = Scheduler()

    assert scheduler.state is SchedulerState.CREATED
    assert scheduler.is_ready is False


def test_scheduler_initializes_to_ready():
    scheduler = Scheduler()

    scheduler.initialize()

    assert scheduler.state is SchedulerState.READY
    assert scheduler.is_ready is True


def test_scheduler_cannot_be_initialized_twice():
    scheduler = Scheduler()

    scheduler.initialize()

    with pytest.raises(SchedulerStateError):
        scheduler.initialize()


def test_scheduler_can_be_stopped_after_initialization():
    scheduler = Scheduler()

    scheduler.initialize()
    scheduler.stop()

    assert scheduler.state is SchedulerState.STOPPED
    assert scheduler.is_ready is False


def test_scheduler_cannot_be_stopped_before_initialization():
    scheduler = Scheduler()

    with pytest.raises(SchedulerStateError):
        scheduler.stop()


def test_stopping_scheduler_twice_is_safe():
    scheduler = Scheduler()

    scheduler.initialize()
    scheduler.stop()
    scheduler.stop()

    assert scheduler.state is SchedulerState.STOPPED


def test_job_can_be_registered():
    scheduler = Scheduler()
    scheduler.initialize()

    job = Job(job_id="test-job", func=lambda: None, schedule=time(6, 0))

    scheduler.register_job(job)

    assert scheduler.has_job("test-job")


def test_registered_job_can_be_looked_up():
    scheduler = Scheduler()
    scheduler.initialize()

    job = Job(job_id="test-job", func=lambda: None, schedule=time(6, 0))

    scheduler.register_job(job)

    registered_job = scheduler.get_job("test-job")

    assert registered_job == job


def test_job_registry_tracks_registered_job():
    scheduler = Scheduler()
    scheduler.initialize()

    job = Job(job_id="test-job", func=lambda: None, schedule=time(6, 0))

    scheduler.register_job(job)

    assert scheduler.has_job("test-job") is True
    assert scheduler.has_job("unknown-job") is False


def test_duplicate_job_registration_raises_duplicate_job_error():
    scheduler = Scheduler()
    scheduler.initialize()

    job = Job(job_id="test-job", func=lambda: None, schedule=time(6, 0))

    scheduler.register_job(job)

    with pytest.raises(DuplicateJobError):
        scheduler.register_job(job)


def test_duplicate_job_does_not_corrupt_scheduler_state():
    scheduler = Scheduler()
    scheduler.initialize()

    job = Job(job_id="test-job", func=lambda: None, schedule=time(6, 0))

    scheduler.register_job(job)

    with pytest.raises(DuplicateJobError):
        scheduler.register_job(job)

    assert scheduler.state is SchedulerState.READY
    assert scheduler.has_job("test-job") is True
    assert scheduler.get_job("test-job") == job


def test_scheduled_job_executes_when_schedule_is_reached():
    executed = []

    def job():
        executed.append(True)
        return "success"

    scheduler = Scheduler()
    scheduler.initialize()

    scheduler.register_job(
        Job(
            job_id="daily_digest",
            func=job,
            schedule=time(6, 0),
        )
    )

    result = scheduler.execute_scheduled_job(
        "daily_digest",
        time(6, 0),
    )

    assert executed == [True]
    assert result == "success"


def test_scheduled_job_does_not_execute_before_schedule():
    executed = []

    def job():
        executed.append(True)
        return "success"

    scheduler = Scheduler()
    scheduler.initialize()

    scheduler.register_job(
        Job(
            job_id="daily_digest",
            func=job,
            schedule=time(6, 0),
        )
    )

    result = scheduler.execute_scheduled_job(
        "daily_digest",
        time(5, 0),
    )

    assert executed == []
    assert result is None


def test_scheduled_job_failure_is_reported_and_propagated(caplog):
    error = RuntimeError("Job failed")

    def job():
        raise error

    scheduler = Scheduler()
    scheduler.initialize()

    scheduler.register_job(
        Job(
            job_id="daily_digest",
            func=job,
            schedule=time(6, 0),
        )
    )

    with caplog.at_level(logging.ERROR):
        with pytest.raises(RuntimeError, match="Job failed"):
            scheduler.execute_scheduled_job(
                "daily_digest",
                time(6, 0),
            )

    assert any(
        record.levelno == logging.ERROR and record.name == "app.core.exceptions"
        for record in caplog.records
    )
