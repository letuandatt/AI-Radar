"""Tests for GitHub Fetcher implementation."""

from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.fetchers.exceptions import FetchTimeoutError, GitHubAPIError, NetworkError
from app.fetchers.github import GitHubFetcher
from app.models.source import GitHubRepository


@pytest.fixture
def mock_repo():
    """Provide a mock GitHub repository."""
    return GitHubRepository(name="test_repo", owner="test_owner", repo="test_repo_name")


@pytest.fixture(autouse=True)
def mock_settings():
    """Mock application settings to avoid dependency on .env file during tests."""
    with patch("app.fetchers.github.get_settings") as mock_get_settings:
        settings = MagicMock()
        settings.fetch_timeout = 10.0
        settings.github_token = "test_token_123"
        mock_get_settings.return_value = settings
        yield mock_get_settings


@pytest.fixture
def fetcher():
    """Provide a GitHubFetcher instance."""
    return GitHubFetcher()


# --- Success Scenario ---


@patch("app.fetchers.github.httpx.get")
def test_fetch_json_success(mock_get, mock_repo, fetcher):
    """Verify that a successful API request returns parsed JSON and correct headers."""
    mock_response = MagicMock()
    mock_response.json.return_value = [{"sha": "abc123", "message": "Initial commit"}]
    mock_response.raise_for_status = MagicMock()
    mock_get.return_value = mock_response

    result = fetcher.fetch_json(mock_repo, "commits")

    assert result == [{"sha": "abc123", "message": "Initial commit"}]
    mock_get.assert_called_once()

    # Verify headers
    call_args = mock_get.call_args

    call_kwargs = call_args.kwargs
    headers = call_kwargs["headers"]
    assert headers["Accept"] == "application/vnd.github.v3+json"
    assert headers["User-Agent"] == "AI-Radar-App"
    assert headers["Authorization"] == "token test_token_123"

    # Verify URL construction
    assert "repos/test_owner/test_repo_name/commits" in call_args.args[0]


# --- HTTP Error Scenarios ---


@patch("app.fetchers.github.httpx.get")
def test_fetch_json_auth_error(mock_get, mock_repo, fetcher):
    """Verify that a 401 Unauthorized error is translated to GitHubAPIError."""
    mock_response = MagicMock()
    mock_response.status_code = 401
    mock_response.headers = {}
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "Unauthorized", request=MagicMock(), response=mock_response
    )
    mock_get.return_value = mock_response

    with pytest.raises(GitHubAPIError, match="401"):
        fetcher.fetch_json(mock_repo, "commits")


@patch("app.fetchers.github.httpx.get")
def test_fetch_json_not_found(mock_get, mock_repo, fetcher):
    """Verify that a 404 Not Found error is translated to GitHubAPIError."""
    mock_response = MagicMock()
    mock_response.status_code = 404
    mock_response.headers = {}
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "Not Found", request=MagicMock(), response=mock_response
    )
    mock_get.return_value = mock_response

    with pytest.raises(GitHubAPIError, match="404"):
        fetcher.fetch_json(mock_repo, "commits")


@patch("app.fetchers.github.httpx.get")
def test_fetch_json_rate_limit_exceeded(mock_get, mock_repo, fetcher):
    """Verify that a 403 with rate limit header is correctly identified."""
    mock_response = MagicMock()
    mock_response.status_code = 403
    mock_response.headers = {"X-RateLimit-Remaining": "0"}
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "Forbidden", request=MagicMock(), response=mock_response
    )
    mock_get.return_value = mock_response

    with pytest.raises(GitHubAPIError, match="Rate limit exceeded"):
        fetcher.fetch_json(mock_repo, "commits")


# --- Network & Timeout Scenarios ---


@patch("app.fetchers.github.httpx.get")
def test_fetch_json_timeout(mock_get, mock_repo, fetcher):
    """Verify that a timeout exception is translated to FetchTimeoutError."""
    mock_get.side_effect = httpx.TimeoutException("Connection timed out")

    with pytest.raises(FetchTimeoutError):
        fetcher.fetch_json(mock_repo, "commits")


@patch("app.fetchers.github.httpx.get")
def test_fetch_json_network_error(mock_get, mock_repo, fetcher):
    """Verify that a network error is translated to NetworkError."""
    mock_get.side_effect = httpx.ConnectError("Connection refused")

    with pytest.raises(NetworkError):
        fetcher.fetch_json(mock_repo, "commits")
