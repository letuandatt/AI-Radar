"""Tests for Hugging Face Fetcher implementation."""

from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.fetchers.exceptions import FetchTimeoutError, HuggingFaceAPIError, NetworkError
from app.fetchers.huggingface import HuggingFaceFetcher
from app.models.source import HFSource, HFSourceType


@pytest.fixture
def mock_dataset_source():
    """Provide a mock Hugging Face dataset source."""
    return HFSource(name="squad", resource_id="rajpurkar/squad", source_type=HFSourceType.DATASET)


@pytest.fixture
def mock_model_source():
    """Provide a mock Hugging Face model source."""
    return HFSource(name="bert", resource_id="google/bert", source_type=HFSourceType.MODEL)


@pytest.fixture(autouse=True)
def mock_settings():
    """Mock application settings to avoid dependency on .env file during tests."""
    with patch("app.fetchers.huggingface.get_settings") as mock_get_settings:
        settings = MagicMock()
        settings.fetch_timeout = 10.0
        settings.hf_token = "hf_test_token_123"
        mock_get_settings.return_value = settings
        yield mock_get_settings


@pytest.fixture
def fetcher():
    """Provide a HuggingFaceFetcher instance."""
    return HuggingFaceFetcher()


# --- Success Scenarios ---


@patch("app.fetchers.huggingface.httpx.get")
def test_fetch_json_success_dataset(mock_get, mock_dataset_source, fetcher):
    """Verify that fetching a dataset returns parsed JSON and correct URL/headers."""
    mock_response = MagicMock()
    mock_response.json.return_value = {"id": "rajpurkar/squad", "description": "SQuAD dataset"}
    mock_response.raise_for_status = MagicMock()
    mock_get.return_value = mock_response

    result = fetcher.fetch_json(mock_dataset_source)

    assert result == {"id": "rajpurkar/squad", "description": "SQuAD dataset"}

    # Verify URL construction for DATASET
    call_args = mock_get.call_args
    assert "api/datasets/rajpurkar/squad" in call_args.args[0]

    # Verify headers
    headers = call_args.kwargs["headers"]
    assert headers["Authorization"] == "Bearer hf_test_token_123"


@patch("app.fetchers.huggingface.httpx.get")
def test_fetch_json_success_model(mock_get, mock_model_source, fetcher):
    """Verify that fetching a model returns parsed JSON and correct URL."""
    mock_response = MagicMock()
    mock_response.json.return_value = {"id": "google/bert", "pipeline_tag": "fill-mask"}
    mock_response.raise_for_status = MagicMock()
    mock_get.return_value = mock_response

    result = fetcher.fetch_json(mock_model_source)

    assert result == {"id": "google/bert", "pipeline_tag": "fill-mask"}

    # Verify URL construction for MODEL
    call_args = mock_get.call_args
    assert "api/models/google/bert" in call_args.args[0]


# --- HTTP Error Scenarios ---


@patch("app.fetchers.huggingface.httpx.get")
def test_fetch_json_auth_error(mock_get, mock_model_source, fetcher):
    """Verify that a 401 Unauthorized error is translated to HuggingFaceAPIError."""
    mock_response = MagicMock()
    mock_response.status_code = 401
    mock_response.headers = {}
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "Unauthorized", request=MagicMock(), response=mock_response
    )
    mock_get.return_value = mock_response

    with pytest.raises(HuggingFaceAPIError, match="401"):
        fetcher.fetch_json(mock_model_source)


@patch("app.fetchers.huggingface.httpx.get")
def test_fetch_json_not_found(mock_get, mock_model_source, fetcher):
    """Verify that a 404 Not Found error is translated to HuggingFaceAPIError."""
    mock_response = MagicMock()
    mock_response.status_code = 404
    mock_response.headers = {}
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "Not Found", request=MagicMock(), response=mock_response
    )
    mock_get.return_value = mock_response

    with pytest.raises(HuggingFaceAPIError, match="404"):
        fetcher.fetch_json(mock_model_source)


# --- Network & Timeout Scenarios ---


@patch("app.fetchers.huggingface.httpx.get")
def test_fetch_json_timeout(mock_get, mock_model_source, fetcher):
    """Verify that a timeout exception is translated to FetchTimeoutError."""
    mock_get.side_effect = httpx.TimeoutException("Connection timed out")

    with pytest.raises(FetchTimeoutError):
        fetcher.fetch_json(mock_model_source)


@patch("app.fetchers.huggingface.httpx.get")
def test_fetch_json_network_error(mock_get, mock_model_source, fetcher):
    """Verify that a network error is translated to NetworkError."""
    mock_get.side_effect = httpx.ConnectError("Connection refused")

    with pytest.raises(NetworkError):
        fetcher.fetch_json(mock_model_source)
