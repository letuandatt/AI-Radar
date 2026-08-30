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
        self._token = settings.hf_token

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

    def fetch_daily_papers(self, date: str | None = None) -> list[dict]:
        """Fetch daily curated papers from HuggingFace Daily Papers API.

        This is a goldmine for discovering important new AI research papers
        curated by the HuggingFace team.

        Endpoint: GET https://huggingface.co/api/daily_papers

        Returns:
            List of paper dictionaries.
        """
        url = f"{self.BASE_URL}/daily_papers"
        params: dict[str, str] = {}
        if date:
            params["date"] = date

        logger.info("Fetching HuggingFace Daily Papers (date=%s)", date or "latest")

        try:
            response = httpx.get(url, headers=self._headers, timeout=self._timeout, params=params)
            response.raise_for_status()
            data: list[dict] = response.json()
            logger.info("Fetched %d daily papers", len(data))
            return data

        except httpx.TimeoutException as error:
            logger.error("Timeout fetching daily papers: %s", error)
            raise FetchTimeoutError("Timeout fetching daily papers") from error

        except httpx.HTTPStatusError as error:
            status = error.response.status_code
            self._handle_http_error(status, url, error)

        except httpx.RequestError as error:
            logger.error("Network error fetching daily papers: %s", error)
            raise NetworkError("Network error fetching daily papers") from error

        return []

    def fetch_trending_models(self, limit: int = 20) -> list[dict]:
        """Fetch trending models from HuggingFace API.

        Args:
            limit: Maximum number of models to return.

        Returns:
            List of model metadata dictionaries.
        """
        url = f"{self.BASE_URL}/models"
        params: dict[str, str | int] = {"sort": "trending", "limit": limit}
        logger.info("Fetching trending models (limit=%d)", limit)

        try:
            response = httpx.get(url, headers=self._headers, timeout=self._timeout, params=params)
            response.raise_for_status()
            data: list[dict] = response.json()
            logger.info("Fetched %d trending models", len(data))
            return data

        except httpx.TimeoutException as error:
            logger.error("Timeout fetching trending models: %s", error)
            raise FetchTimeoutError("Timeout fetching trending models") from error

        except httpx.HTTPStatusError as error:
            status = error.response.status_code
            self._handle_http_error(status, url, error)

        except httpx.RequestError as error:
            logger.error("Network error fetching trending models: %s", error)
            raise NetworkError("Network error fetching trending models") from error

        return []

    def fetch_trending_datasets(self, limit: int = 20) -> list[dict]:
        """Fetch trending datasets from HuggingFace API.

        Args:
            limit: Maximum number of datasets to return.

        Returns:
            List of dataset metadata dictionaries.
        """
        url = f"{self.BASE_URL}/datasets"
        params: dict[str, str | int] = {"sort": "trending", "limit": limit}
        logger.info("Fetching trending datasets (limit=%d)", limit)

        try:
            response = httpx.get(url, headers=self._headers, timeout=self._timeout, params=params)
            response.raise_for_status()
            data: list[dict] = response.json()
            logger.info("Fetched %d trending datasets", len(data))
            return data

        except httpx.TimeoutException as error:
            logger.error("Timeout fetching trending datasets: %s", error)
            raise FetchTimeoutError("Timeout fetching trending datasets") from error

        except httpx.HTTPStatusError as error:
            status = error.response.status_code
            self._handle_http_error(status, url, error)

        except httpx.RequestError as error:
            logger.error("Network error fetching trending datasets: %s", error)
            raise NetworkError("Network error fetching trending datasets") from error

        return []

    def fetch_papers_by_date(self, date: str) -> list[dict]:
        """Fetch papers published on a specific date from HuggingFace.

        Unlike daily_papers (which returns curated/featured papers),
        this endpoint returns papers actually submitted on that date.

        Endpoint: GET https://huggingface.co/api/papers?date=YYYY-MM-DD

        Args:
            date: Date string in YYYY-MM-DD format (e.g., "2026-08-30").

        Returns:
            List of paper dictionaries published on that date.
        """
        url = f"{self.BASE_URL}/papers"
        params: dict[str, str] = {"date": date}
        logger.info("Fetching HuggingFace papers for date: %s", date)

        try:
            response = httpx.get(url, headers=self._headers, timeout=self._timeout, params=params)
            response.raise_for_status()
            data: list[dict] = response.json()
            logger.info("Fetched %d papers for %s", len(data), date)
            return data

        except httpx.TimeoutException as error:
            logger.error("Timeout fetching papers for %s: %s", date, error)
            raise FetchTimeoutError(f"Timeout fetching papers for {date}") from error

        except httpx.HTTPStatusError as error:
            status = error.response.status_code
            self._handle_http_error(status, url, error)

        except httpx.RequestError as error:
            logger.error("Network error fetching papers for %s: %s", date, error)
            raise NetworkError(f"Network error fetching papers for {date}") from error

        return []
