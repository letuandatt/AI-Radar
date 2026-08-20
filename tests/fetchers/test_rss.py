"""Tests for RSS Fetcher implementation."""

from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.fetchers.exceptions import FetchTimeoutError, HTTPStatusError, NetworkError
from app.fetchers.rss import RSSFetcher
from app.models.source import RSSSource


@pytest.fixture
def mock_source():
    """Provide a mock RSS source."""
    return RSSSource(name="test_feed", url="http://test.com/rss")


@pytest.fixture
def fetcher():
    """Provide an RSSFetcher instance with a short timeout."""
    return RSSFetcher(timeout=5.0)


# --- Success Scenario ---


@patch("app.fetchers.rss.httpx.get")
def test_fetch_raw_success(mock_get, mock_source, fetcher):
    """Verify that a successful HTTP request returns the raw text content."""
    mock_response = MagicMock()
    mock_response.text = "<rss><channel><title>Test</title></channel></rss>"
    mock_response.raise_for_status = MagicMock()  # Do nothing on success
    mock_get.return_value = mock_response

    result = fetcher.fetch_raw(mock_source)

    assert result == "<rss><channel><title>Test</title></channel></rss>"
    mock_get.assert_called_once_with("http://test.com/rss", timeout=5.0)
    mock_response.raise_for_status.assert_called_once()


# --- Timeout Scenario ---


@patch("app.fetchers.rss.httpx.get")
def test_fetch_raw_timeout(mock_get, mock_source, fetcher):
    """Verify that a timeout exception is translated to FetchTimeoutError."""
    mock_get.side_effect = httpx.TimeoutException("Connection timed out")

    with pytest.raises(FetchTimeoutError, match="Timeout fetching http://test.com/rss"):
        fetcher.fetch_raw(mock_source)


# --- HTTP Status Error Scenario ---


@patch("app.fetchers.rss.httpx.get")
def test_fetch_raw_http_error(mock_get, mock_source, fetcher):
    """Verify that an HTTP 4xx/5xx error is translated to HTTPStatusError."""
    # Create a mock response with a 404 status code
    mock_response = MagicMock()
    mock_response.status_code = 404

    # Simulate httpx raising HTTPStatusError when raise_for_status() is called
    mock_request = MagicMock()
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "Not Found", request=mock_request, response=mock_response
    )
    mock_get.return_value = mock_response

    with pytest.raises(HTTPStatusError, match="HTTP 404 fetching http://test.com/rss"):
        fetcher.fetch_raw(mock_source)


# --- Network Error Scenario ---


@patch("app.fetchers.rss.httpx.get")
def test_fetch_raw_network_error(mock_get, mock_source, fetcher):
    """Verify that a network error (e.g., DNS failure) is translated to NetworkError."""
    # ConnectError is a subclass of RequestError in httpx
    mock_get.side_effect = httpx.ConnectError("Connection refused")

    with pytest.raises(NetworkError, match="Request error fetching http://test.com/rss"):
        fetcher.fetch_raw(mock_source)
