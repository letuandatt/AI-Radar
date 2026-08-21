"""Hugging Face Data Fetcher implementation.

This module provides the concrete implementation for retrieving data
from the Hugging Face Hub API, handling authentication and specific
API error codes.
"""

from datetime import datetime

import httpx

from app.config.settings import get_settings
from app.core.logger import get_logger
from app.fetchers.exceptions import (
    FetchTimeoutError,
    HuggingFaceAPIError,
    NetworkError,
)
from app.models.article import RawArticle
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


class HuggingFaceParser:
    """Parses JSON metadata from Hugging Face API into RawArticle models.

    This parser handles the specific JSON structures returned by the
    Hugging Face Hub API for datasets and models, transforming them into
    the standardized RawArticle format for knowledge extraction.
    """

    def parse(self, data: dict, source: HFSource) -> list[RawArticle]:
        """Parse Hugging Face metadata JSON into a list of RawArticle models.

        Note: Hugging Face API returns a single dictionary per resource,
        not a list. This method returns a list with 0 or 1 element for
        consistency with other parsers.

        Args:
            data: The metadata dictionary from Hugging Face API.
            source: The source configuration this data belongs to.

        Returns:
            A list containing 0 or 1 RawArticle instance.
        """
        resource_id = data.get("id") or data.get("modelId") or data.get("datasetId")

        # Defensive Parsing: Skip if essential identifier is missing
        if not resource_id:
            logger.warning(
                "Skipping HF resource from %s: missing 'id', 'modelId', or 'datasetId'", source.name
            )
            return []

        # Extract title (prefer cardData.title, fallback to resource_id)
        card_data = data.get("cardData") or {}
        title = card_data.get("title") or resource_id

        # Build URL based on source type
        if source.source_type == HFSourceType.DATASET:
            url = f"https://huggingface.co/datasets/{resource_id}"
        else:  # MODEL
            url = f"https://huggingface.co/{resource_id}"

        # Extract content (description)
        content = data.get("description") or card_data.get("description") or ""

        # Parse last modified date
        published_date = self._parse_iso_date(data.get("lastModified"))

        article = RawArticle(
            title=title,
            url=url,
            content=content,
            published_date=published_date,
            source_name=source.name,
        )

        logger.info("Parsed HF resource: %s (%s)", title, source.name)
        return [article]

    def _parse_iso_date(self, date_str: str | None) -> datetime | None:
        """Convert Hugging Face's ISO 8601 date string to a datetime object.

        Hugging Face returns dates like "2024-03-15T10:00:00.000Z".
        Python's fromisoformat() doesn't handle the 'Z' suffix until Python 3.11,
        so we replace it with '+00:00' for compatibility.
        """
        if not date_str:
            return None
        try:
            # Handle milliseconds and 'Z' suffix
            if date_str.endswith("Z"):
                date_str = date_str[:-1] + "+00:00"
            # Remove milliseconds if present (e.g., ".000")
            if "." in date_str:
                date_str = date_str.split(".")[0] + date_str[date_str.rfind("+") :]
            return datetime.fromisoformat(date_str)
        except ValueError as error:
            logger.warning("Failed to parse date '%s': %s", date_str, error)
            return None
