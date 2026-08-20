"""RSS Feed Fetcher implementation.

This module provides the concrete implementation of the Fetcher protocol
for retrieving raw RSS feed content over HTTP.
"""

import httpx

from app.core import get_logger
from app.fetchers.exceptions import (
    FetchTimeoutError,
    HTTPStatusError,
    NetworkError,
)
from app.models.source import RSSSource

logger = get_logger(__name__)


class RSSFetcher:
    """Fetches raw RSS feed content using HTTP GET requests.

    This implementation uses the `httpx` library to perform synchronous
    HTTP requests. It handles network errors, timeouts, and HTTP status
    codes, translating them into domain-specific exceptions to decouple
    the business logic from the underlying HTTP library.
    """

    def __init__(self, timeout: float = 10.0) -> None:
        """Initialize the fetcher with a specific timeout.

        Args:
            timeout: The maximum time in seconds to wait for a response.
        """
        self._timeout = timeout

    def fetch_raw(self, source: RSSSource) -> str:
        """Fetch raw XML content from the given RSS source.

        Args:
            source: The RSS source to fetch from.

        Returns:
            The raw string content of the RSS feed.

        Raises:
            FetchTimeoutError: If the request exceeds the time limit.
            NetworkError: If the connection cannot be established.
            HTTPStatusError: If the server returns a 4xx or 5xx status code.
        """
        logger.info("Fetching RSS feed from: %s", source.url)

        try:
            # Use httpx.get for simplicity.
            # (Connection pooling via httpx.Client can be added later if needed).
            response = httpx.get(source.url, timeout=self._timeout)

            # Automatically raise an exception for 4xx/5xx responses
            response.raise_for_status()

            return response.text

        except httpx.TimeoutException as error:
            logger.error("Timeout while fetching %s: %s", source.url, error)
            raise FetchTimeoutError(f"Timeout fetching {source.url}") from error

        except httpx.HTTPStatusError as error:
            logger.error("HTTP error %s while fetching %s", error.response.status_code, source.url)
            raise HTTPStatusError(
                f"HTTP {error.response.status_code} fetching {source.url}"
            ) from error

        except httpx.RequestError as error:
            # Catch-all for other httpx network-related errors
            # (e.g., ConnectError, DNS resolution failure)
            logger.error("Request error while fetching %s: %s", source.url, error)
            raise NetworkError(f"Request error fetching {source.url}") from error
