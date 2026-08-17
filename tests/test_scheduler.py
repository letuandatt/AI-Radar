import pytest

from app.core.scheduler import Scheduler, SchedulerState, SchedulerStateError


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
