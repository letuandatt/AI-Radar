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

    job = Job(job_id="test-job", func=lambda: None)

    scheduler.register_job(job)

    assert scheduler.has_job("test-job")


def test_registered_job_can_be_looked_up():
    scheduler = Scheduler()
    scheduler.initialize()

    job = Job(job_id="test-job", func=lambda: None)

    scheduler.register_job(job)

    registered_job = scheduler.get_job("test-job")

    assert registered_job == job


def test_job_registry_tracks_registered_job():
    scheduler = Scheduler()
    scheduler.initialize()

    job = Job(job_id="test-job", func=lambda: None)

    scheduler.register_job(job)

    assert scheduler.has_job("test-job") is True
    assert scheduler.has_job("unknown-job") is False


def test_duplicate_job_registration_raises_duplicate_job_error():
    scheduler = Scheduler()
    scheduler.initialize()

    job = Job(job_id="test-job", func=lambda: None)

    scheduler.register_job(job)

    with pytest.raises(DuplicateJobError):
        scheduler.register_job(job)


def test_duplicate_job_does_not_corrupt_scheduler_state():
    scheduler = Scheduler()
    scheduler.initialize()

    job = Job(job_id="test-job", func=lambda: None)

    scheduler.register_job(job)

    with pytest.raises(DuplicateJobError):
        scheduler.register_job(job)

    assert scheduler.state is SchedulerState.READY
    assert scheduler.has_job("test-job") is True
    assert scheduler.get_job("test-job") == job
