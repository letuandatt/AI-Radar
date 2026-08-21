"""Hugging Face Data Fetcher implementation.

This module provides the concrete implementation for retrieving data
from the Hugging Face Hub API, handling authentication and specific
API error codes.
"""

import httpx

from app.config.settings import get_settings
from app.core.logger import get_logger
from app.fetchers.exceptions import (
    FetchTimeoutError,
    HuggingFaceAPIError,
    NetworkError,
)
from app.models.source import HFSource, HFSourceType

logger = get_logger(__name__)


class HuggingFaceFetcher:
    """Fetches data from the Hugging Face Hub API.

    This implementation uses `httpx` to perform synchronous HTTP requests.
    It automatically handles Hugging Face-specific headers, authentication
    via API Token, and translates HTTP errors into domain-specific exceptions.
    """

    BASE_URL = "https://huggingface.co/api"

    def __init__(self, timeout: float | None = None) -> None:
        """Initialize the fetcher with Hugging Face-specific headers and auth."""
        settings = get_settings()
        self._timeout = timeout or settings.fetch_timeout
        self._token = settings.hf_token  # type: ignore[attr-defined]

        self._headers = {
            "Accept": "application/json",
        }
        if self._token:
            self._headers["Authorization"] = f"Bearer {self._token}"
            logger.debug("HuggingFaceFetcher initialized with authentication token.")
        else:
            logger.warning(
                "HuggingFaceFetcher initialized WITHOUT token. "
                "Access to private repos will be limited."
            )

    def fetch_json(self, source: HFSource) -> dict:
        """Fetch JSON data from the Hugging Face API for the given source.

        Args:
            source: The Hugging Face source to fetch from.

        Returns:
            A dictionary representing the JSON response.
        """
        # Build URL based on source type
        if source.source_type == HFSourceType.DATASET:
            url = f"{self.BASE_URL}/datasets/{source.resource_id}"
        else:  # MODEL
            url = f"{self.BASE_URL}/models/{source.resource_id}"

        logger.info("Fetching Hugging Face data: %s (%s)", source.name, url)

        try:
            response = httpx.get(url, headers=self._headers, timeout=self._timeout)
            response.raise_for_status()
            data: dict = response.json()
            return data

        except httpx.TimeoutException as error:
            logger.error("Timeout while fetching %s: %s", url, error)
            raise FetchTimeoutError(f"Timeout fetching {url}") from error

        except httpx.HTTPStatusError as error:
            status = error.response.status_code
            self._handle_http_error(status, url, error)

        except httpx.RequestError as error:
            logger.error("Network error while fetching %s: %s", url, error)
            raise NetworkError(f"Network error fetching {url}") from error

        # Fallback (should not be reached)
        return {}

    def _handle_http_error(self, status: int, url: str, error: httpx.HTTPStatusError) -> None:
        """Translate Hugging Face HTTP status codes into HuggingFaceAPIError."""
        error_message = f"Hugging Face API error {status} for {url}"

        if status == 401 or status == 403:
            error_message += " (Authentication failed or forbidden)"
        elif status == 404:
            error_message += " (Resource not found or private without access)"
        elif status == 429:
            error_message += " (Rate limit exceeded)"

        logger.error(error_message)
        raise HuggingFaceAPIError(error_message) from error
