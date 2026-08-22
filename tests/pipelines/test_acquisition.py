"""Tests for the Default Acquisition Pipeline implementation."""

from unittest.mock import MagicMock, patch

import pytest

from app.fetchers.exceptions import NetworkError
from app.models.source import GitHubRepository, HFSource, HFSourceType, RSSSource
from app.pipelines.acquisition import DefaultAcquisitionPipeline

# --- Fixtures ---


@pytest.fixture
def mock_rss_registry():
    registry = MagicMock()
    registry.get_all.return_value = [
        RSSSource(name="rss_techcrunch", url="https://techcrunch.com/feed/")
    ]
    return registry


@pytest.fixture
def mock_github_registry():
    registry = MagicMock()
    registry.get_all.return_value = [
        GitHubRepository(name="fastapi", owner="tiangolo", repo="fastapi")
    ]
    return registry


@pytest.fixture
def mock_hf_registry():
    registry = MagicMock()
    registry.get_all.return_value = [
        HFSource(
            name="bert", resource_id="google-bert/bert-base-uncased", source_type=HFSourceType.MODEL
        )
    ]
    return registry


# --- Test Cases ---


# We patch the Fetcher/Parser classes where they are USED (in app.pipelines.acquisition)
@patch("app.pipelines.acquisition.HuggingFaceParser")
@patch("app.pipelines.acquisition.HuggingFaceFetcher")
@patch("app.pipelines.acquisition.GitHubParser")
@patch("app.pipelines.acquisition.GitHubFetcher")
@patch("app.pipelines.acquisition.RSSParser")
@patch("app.pipelines.acquisition.RSSFetcher")
def test_pipeline_run_success(
    mock_rss_fetcher_cls,
    mock_rss_parser_cls,
    mock_gh_fetcher_cls,
    mock_gh_parser_cls,
    mock_hf_fetcher_cls,
    mock_hf_parser_cls,
    mock_rss_registry,
    mock_github_registry,
    mock_hf_registry,
):
    """Verify that the pipeline successfully orchestrates all sources and aggregates results."""
    # Setup RSS mocks (returns 2 articles)
    mock_rss_fetcher_cls.return_value.fetch_raw.return_value = "<rss>data</rss>"
    mock_rss_parser_cls.return_value.parse.return_value = [MagicMock(), MagicMock()]

    # Setup GitHub mocks (returns 1 commit + 3 issues = 4 articles)
    mock_gh_fetcher_cls.return_value.fetch_commits.return_value = [{"sha": "123"}]
    mock_gh_parser_cls.return_value.parse_commits.return_value = [MagicMock()]
    mock_gh_fetcher_cls.return_value.fetch_issues.return_value = [{"number": 1}]
    mock_gh_parser_cls.return_value.parse_issues.return_value = [
        MagicMock(),
        MagicMock(),
        MagicMock(),
    ]

    # Setup HuggingFace mocks (returns 1 article)
    mock_hf_fetcher_cls.return_value.fetch_json.return_value = {"id": "test/model"}
    mock_hf_parser_cls.return_value.parse.return_value = [MagicMock()]

    # Initialize and run pipeline
    pipeline = DefaultAcquisitionPipeline(mock_rss_registry, mock_github_registry, mock_hf_registry)

    result = pipeline.run()

    # Assertions
    assert result.total_sources == 3
    assert result.successful_sources == 3
    assert result.failed_sources == 0
    assert result.total_articles == 7  # 2 (RSS) + 1 (Commit) + 3 (Issues) + 1 (HF)
    assert result.execution_time >= 0
    assert len(result.errors) == 0


@patch("app.pipelines.acquisition.HuggingFaceParser")
@patch("app.pipelines.acquisition.HuggingFaceFetcher")
@patch("app.pipelines.acquisition.GitHubParser")
@patch("app.pipelines.acquisition.GitHubFetcher")
@patch("app.pipelines.acquisition.RSSParser")
@patch("app.pipelines.acquisition.RSSFetcher")
def test_pipeline_fault_tolerance(
    mock_rss_fetcher_cls,
    mock_rss_parser_cls,
    mock_gh_fetcher_cls,
    mock_gh_parser_cls,
    mock_hf_fetcher_cls,
    mock_hf_parser_cls,
    mock_rss_registry,
    mock_github_registry,
    mock_hf_registry,
):
    """Verify that if one source fails, the pipeline continues and logs the error."""
    # RSS and HF succeed
    mock_rss_fetcher_cls.return_value.fetch_raw.return_value = "data"
    mock_rss_parser_cls.return_value.parse.return_value = [MagicMock()]

    mock_hf_fetcher_cls.return_value.fetch_json.return_value = {"id": "test"}
    mock_hf_parser_cls.return_value.parse.return_value = [MagicMock()]

    # GitHub FAILS with a Network Error
    mock_gh_fetcher_cls.return_value.fetch_commits.side_effect = NetworkError(
        "Connection timed out"
    )

    pipeline = DefaultAcquisitionPipeline(mock_rss_registry, mock_github_registry, mock_hf_registry)

    result = pipeline.run()

    # Assertions
    assert result.total_sources == 3
    assert result.successful_sources == 2  # RSS and HF
    assert result.failed_sources == 1  # GitHub
    assert result.total_articles == 2  # 1 (RSS) + 1 (HF)

    # Check error logging
    assert len(result.errors) == 1
    error = result.errors[0]
    assert error.source_name == "fastapi"
    assert error.source_type == "github"
    assert error.error_type == "NetworkError"
    assert "Connection timed out" in error.error_message


@patch("app.pipelines.acquisition.HuggingFaceParser")
@patch("app.pipelines.acquisition.HuggingFaceFetcher")
@patch("app.pipelines.acquisition.GitHubParser")
@patch("app.pipelines.acquisition.GitHubFetcher")
@patch("app.pipelines.acquisition.RSSParser")
@patch("app.pipelines.acquisition.RSSFetcher")
def test_pipeline_empty_registries(
    mock_rss_fetcher_cls,
    mock_rss_parser_cls,
    mock_gh_fetcher_cls,
    mock_gh_parser_cls,
    mock_hf_fetcher_cls,
    mock_hf_parser_cls,
):
    """Verify that the pipeline handles empty registries gracefully."""
    mock_rss_registry = MagicMock()
    mock_rss_registry.get_all.return_value = []

    mock_github_registry = MagicMock()
    mock_github_registry.get_all.return_value = []

    mock_hf_registry = MagicMock()
    mock_hf_registry.get_all.return_value = []

    pipeline = DefaultAcquisitionPipeline(mock_rss_registry, mock_github_registry, mock_hf_registry)

    result = pipeline.run()

    assert result.total_sources == 0
    assert result.successful_sources == 0
    assert result.failed_sources == 0
    assert result.total_articles == 0
    assert len(result.errors) == 0


@patch("app.pipelines.acquisition.HuggingFaceParser")
@patch("app.pipelines.acquisition.HuggingFaceFetcher")
@patch("app.pipelines.acquisition.GitHubParser")
@patch("app.pipelines.acquisition.GitHubFetcher")
@patch("app.pipelines.acquisition.RSSParser")
@patch("app.pipelines.acquisition.RSSFetcher")
def test_pipeline_scheduler_independence(
    mock_rss_fetcher_cls,
    mock_rss_parser_cls,
    mock_gh_fetcher_cls,
    mock_gh_parser_cls,
    mock_hf_fetcher_cls,
    mock_hf_parser_cls,
    mock_rss_registry,
    mock_github_registry,
    mock_hf_registry,
):
    """Verify that the pipeline can be executed directly without a Scheduler (ARCH-004)."""
    # Setup minimal mocks to prevent actual execution errors
    mock_rss_registry.get_all.return_value = []
    mock_github_registry.get_all.return_value = []
    mock_hf_registry.get_all.return_value = []

    pipeline = DefaultAcquisitionPipeline(mock_rss_registry, mock_github_registry, mock_hf_registry)

    # Calling .run() directly proves it doesn't depend on APScheduler
    result = pipeline.run()

    assert isinstance(result.timestamp, type(result.timestamp))  # Just checking it ran
    assert result.total_sources == 0
