"""Tests for Acquisition Scheduling integration."""

from datetime import datetime, time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.core.application as app_module
from app.core.scheduler import Job, Scheduler, SchedulerState
from app.models.article import RawArticle
from app.models.result import AcquisitionResult


@pytest.fixture(autouse=True)
def reset_registry():
    """Ensure global registry is clean before and after each test."""
    app_module._registry = None
    yield
    app_module._registry = None


@patch("app.core.application.get_settings")
@patch("app.core.application.initialize_source_registry")
@patch("app.core.application.initialize_github_registry")
@patch("app.core.application.initialize_hf_registry")
@patch("app.core.application.get_source_registry")
@patch("app.core.application.get_github_registry")
@patch("app.core.application.get_hf_registry")
@patch("app.core.application.DefaultAcquisitionPipeline")
def test_init_acquisition_registers_job_and_runs_on_startup(
    mock_pipeline_cls,
    mock_get_hf,
    mock_get_gh,
    mock_get_rss,
    mock_init_hf,
    mock_init_gh,
    mock_init_rss,
    mock_get_settings,
):
    """Validate job registration and startup execution."""
    # 1. Setup Settings
    mock_settings = MagicMock()
    mock_settings.acquisition_schedule_time = time(6, 0)
    mock_settings.acquisition_run_on_startup = True
    mock_settings.knowledge_update_enabled = False
    mock_get_settings.return_value = mock_settings

    # 2. Setup Mock Pipeline & Result
    mock_pipeline = MagicMock()
    mock_pipeline_cls.return_value = mock_pipeline
    mock_result = AcquisitionResult(
        timestamp=MagicMock(),
        total_sources=1,
        successful_sources=1,
        failed_sources=0,
        total_articles=5,
        execution_time=1.5,
        errors=[],
    )
    mock_pipeline.run.return_value = mock_result

    # 3. Setup Mock Registry with Scheduler
    mock_scheduler = MagicMock(spec=Scheduler)
    mock_scheduler.state = SchedulerState.READY

    mock_registry = MagicMock()
    mock_registry.get_component.return_value = mock_scheduler
    app_module._registry = mock_registry

    # 4. Execute
    result_pipeline = app_module._init_acquisition()

    # 5. Assertions
    mock_init_rss.assert_called_once_with(mock_settings)
    mock_pipeline_cls.assert_called_once()

    # Verify job registration
    mock_scheduler.register_job.assert_called_once()
    registered_job: Job = mock_scheduler.register_job.call_args[0][0]
    assert registered_job.job_id == "acquisition_pipeline"
    assert registered_job.schedule == time(6, 0)
    assert callable(registered_job.func)

    # Verify run on startup
    mock_pipeline.run.assert_called_once()
    assert result_pipeline == mock_pipeline


@patch("app.core.application.get_settings")
@patch("app.core.application.initialize_source_registry")
@patch("app.core.application.initialize_github_registry")
@patch("app.core.application.initialize_hf_registry")
@patch("app.core.application.get_source_registry")
@patch("app.core.application.get_github_registry")
@patch("app.core.application.get_hf_registry")
@patch("app.core.application.DefaultAcquisitionPipeline")
def test_init_acquisition_skips_run_on_startup_if_disabled(
    mock_pipeline_cls,
    mock_get_hf,
    mock_get_gh,
    mock_get_rss,
    mock_init_hf,
    mock_init_gh,
    mock_init_rss,
    mock_get_settings,
):
    """Validate that pipeline does NOT run on startup if configured False."""
    mock_settings = MagicMock()
    mock_settings.acquisition_schedule_time = time(12, 0)
    mock_settings.acquisition_run_on_startup = False  # DISABLED
    mock_settings.knowledge_update_enabled = False
    mock_get_settings.return_value = mock_settings

    mock_pipeline = MagicMock()
    mock_pipeline_cls.return_value = mock_pipeline

    mock_scheduler = MagicMock(spec=Scheduler)
    mock_scheduler.state = SchedulerState.READY
    mock_registry = MagicMock()
    mock_registry.get_component.return_value = mock_scheduler
    app_module._registry = mock_registry

    # Execute
    app_module._init_acquisition()

    # Assertions
    mock_scheduler.register_job.assert_called_once()
    mock_pipeline.run.assert_not_called()  # Crucial: must NOT be called


# ==============================================================================
# Knowledge Update Wiring Tests (Wiring & Fix Plan A1)
# ==============================================================================


@patch("app.core.application.get_settings")
@patch("app.core.application.initialize_source_registry")
@patch("app.core.application.initialize_github_registry")
@patch("app.core.application.initialize_hf_registry")
@patch("app.core.application.get_source_registry")
@patch("app.core.application.get_github_registry")
@patch("app.core.application.get_hf_registry")
@patch("app.core.application.DefaultAcquisitionPipeline")
def test_knowledge_update_job_forwards_articles_to_processing(
    mock_pipeline_cls,
    mock_get_hf,
    mock_get_gh,
    mock_get_rss,
    mock_init_hf,
    mock_init_gh,
    mock_init_rss,
    mock_get_settings,
):
    """A1: when enabled, the scheduled job chains acquisition -> processing."""
    mock_settings = MagicMock()
    mock_settings.acquisition_schedule_time = time(6, 0)
    mock_settings.acquisition_run_on_startup = False
    mock_settings.knowledge_update_enabled = True
    mock_get_settings.return_value = mock_settings

    acquired_article = RawArticle(
        title="Wired Article",
        url="https://example.com/wired",
        content="Content for wiring test",
        published_date=datetime(2025, 1, 1),
        source_name="test_source",
    )
    mock_result = AcquisitionResult(
        timestamp=MagicMock(),
        total_sources=1,
        successful_sources=1,
        failed_sources=0,
        total_articles=1,
        execution_time=0.5,
        errors=[],
        articles=[acquired_article],
    )
    mock_pipeline = MagicMock()
    mock_pipeline.run.return_value = mock_result
    mock_pipeline_cls.return_value = mock_pipeline

    processing_pipeline = MagicMock()
    processing_pipeline.run_async = AsyncMock(return_value=MagicMock())

    mock_scheduler = MagicMock(spec=Scheduler)
    mock_scheduler.state = SchedulerState.READY

    def _get_component(name: str):
        if name == "scheduler":
            return mock_scheduler
        if name == "processing":
            return processing_pipeline
        raise KeyError(name)

    mock_registry = MagicMock()
    mock_registry.get_component.side_effect = _get_component
    app_module._registry = mock_registry

    app_module._init_acquisition()

    registered_job: Job = mock_scheduler.register_job.call_args[0][0]
    registered_job.func()  # run the chained job

    processing_pipeline.run_async.assert_awaited_once()
    args = processing_pipeline.run_async.await_args.args
    assert acquired_article in args[0]
