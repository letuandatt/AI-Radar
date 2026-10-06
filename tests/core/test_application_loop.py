"""Tests for the A2 scheduled-jobs loop (run_scheduled_cycle + restart guard)."""

from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

from app.core.application import run_scheduled_cycle
from app.core.scheduler import Job, Scheduler

SCHEDULE = datetime(2026, 10, 6, 6, 0)
AT_00_00 = datetime(2026, 10, 6, 0, 0)
AT_06_00 = SCHEDULE
AT_06_01 = SCHEDULE + timedelta(minutes=1)
AT_06_02 = SCHEDULE + timedelta(minutes=2)
NEXT_DAY = SCHEDULE + timedelta(days=1)


def _make_scheduler(state_file: Path | None = None) -> Scheduler:
    scheduler = Scheduler(state_file=state_file)
    scheduler.initialize()
    return scheduler


def _register(scheduler: Scheduler, job_id: str, func) -> None:
    scheduler.register_job(Job(job_id=job_id, func=func, schedule=SCHEDULE.time()))


def test_job_runs_exactly_once_on_schedule() -> None:
    """Fake clock 00:00 -> 06:00 -> 06:01 -> 06:02: job runs exactly once."""
    scheduler = _make_scheduler()
    func = MagicMock()
    _register(scheduler, "acquisition_pipeline", func)

    assert run_scheduled_cycle(scheduler, AT_00_00) == []
    func.assert_not_called()

    assert run_scheduled_cycle(scheduler, AT_06_00) == ["acquisition_pipeline"]
    func.assert_called_once()

    assert run_scheduled_cycle(scheduler, AT_06_01) == []
    assert run_scheduled_cycle(scheduler, AT_06_02) == []
    func.assert_called_once()


def test_failing_job_does_not_stop_remaining_jobs() -> None:
    """Job1 raises → the loop survives and job2 still runs."""
    scheduler = _make_scheduler()
    failing = MagicMock(side_effect=RuntimeError("job exploded"))
    healthy = MagicMock()
    _register(scheduler, "job1", failing)
    _register(scheduler, "job2", healthy)

    executed = run_scheduled_cycle(scheduler, AT_06_00)

    assert executed == ["job1", "job2"]
    healthy.assert_called_once()

    # Both jobs are marked run despite the failure — no same-day retry loop
    assert run_scheduled_cycle(scheduler, AT_06_01) == []


def test_restart_on_same_day_does_not_rerun(
    tmp_path: Path,
) -> None:
    """Last-run dates persist: a fresh Scheduler on the same day skips the job."""
    state_file = tmp_path / "scheduler_state.json"

    first = _make_scheduler(state_file)
    func = MagicMock()
    _register(first, "acquisition_pipeline", func)
    run_scheduled_cycle(first, AT_06_00)
    func.assert_called_once()

    # "Restart": brand-new scheduler instance, same persisted state file
    second = _make_scheduler(state_file)
    func_again = MagicMock()
    _register(second, "acquisition_pipeline", func_again)

    assert run_scheduled_cycle(second, AT_06_02) == []
    func_again.assert_not_called()

    # Next day the job is due again
    assert run_scheduled_cycle(second, NEXT_DAY) == ["acquisition_pipeline"]
    func_again.assert_called_once()


def test_corrupt_state_file_degrades_to_empty() -> None:
    """A corrupt state file must not prevent the scheduler from starting."""
    state_file = Path(__import__("tempfile").gettempdir()) / "corrupt_state_test.json"
    state_file.write_text("not-json{", encoding="utf-8")
    try:
        scheduler = _make_scheduler(state_file)
        assert scheduler.get_last_run_date("anything") is None
    finally:
        state_file.unlink(missing_ok=True)


def test_mark_run_unknown_job_raises() -> None:
    scheduler = _make_scheduler()
    try:
        scheduler.mark_run("ghost", AT_06_00)
        raise AssertionError("expected KeyError")
    except KeyError:
        pass
