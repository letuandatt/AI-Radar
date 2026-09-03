"""GitHub Data Fetcher implementation.

This module provides the concrete implementation for retrieving data
from the GitHub REST API, handling authentication, rate limits, and
specific API error codes.
"""

import httpx

from app.config.settings import get_settings
from app.core.logger import get_logger
from app.fetchers.exceptions import (
    FetchTimeoutError,
    GitHubAPIError,
    NetworkError,
)
from app.models.source import GitHubRepository

logger = get_logger(__name__)


class GitHubFetcher:
    """Fetches data from the GitHub REST API.

    This implementation uses `httpx` to perform synchronous HTTP requests.
    It automatically handles GitHub-specific headers, authentication via
    Personal Access Token (PAT), and translates HTTP errors into domain-specific
    exceptions.
    """

    BASE_URL = "https://api.github.com"

    def __init__(self, timeout: float | None = None) -> None:
        """Initialize the fetcher with GitHub-specific headers and auth."""
        settings = get_settings()
        self._timeout = timeout or settings.fetch_timeout
        self._token = settings.github_token

        self._headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "AI-Radar-App",  # Required by GitHub API guidelines
        }
        if self._token:
            self._headers["Authorization"] = f"token {self._token}"
            logger.debug("GitHubFetcher initialized with authentication token.")
        else:
            logger.warning("GitHubFetcher initialized WITHOUT token. Rate limit is 60 req/hour.")

    def fetch_json(
        self, source: GitHubRepository, endpoint: str, params: dict | None = None
    ) -> list[dict]:
        """Fetch JSON data from a specific GitHub API endpoint.

        Args:
            source: The GitHub repository to fetch from.
            endpoint: The API endpoint (e.g., 'commits', 'issues').
            params: Optional query parameters for the request.

        Returns:
            A list of dictionaries representing the JSON response.
        """
        url = f"{self.BASE_URL}/repos/{source.owner}/{source.repo}/{endpoint}"
        logger.info("Fetching GitHub data: %s/%s", source.name, endpoint)

        try:
            response = httpx.get(url, headers=self._headers, timeout=self._timeout, params=params)
            response.raise_for_status()
            return response.json()  # type: ignore[no-any-return]

        except httpx.TimeoutException as error:
            logger.error("Timeout while fetching %s: %s", url, error)
            raise FetchTimeoutError(f"Timeout fetching {url}") from error

        except httpx.HTTPStatusError as error:
            status = error.response.status_code
            self._handle_http_error(status, url, error)

        except httpx.RequestError as error:
            logger.error("Network error while fetching %s: %s", url, error)
            raise NetworkError(f"Network error fetching {url}") from error

        # Fallback (should not be reached due to raise in except blocks)
        return []

    def _handle_http_error(self, status: int, url: str, error: httpx.HTTPStatusError) -> None:
        """Translate GitHub HTTP status codes into GitHubAPIError."""
        error_message = f"GitHub API error {status} for {url}"

        if status == 401 or status == 403:
            # 403 often means rate limit exceeded or forbidden
            rate_limit_remaining = error.response.headers.get("X-RateLimit-Remaining")
            if rate_limit_remaining == "0":
                error_message += " (Rate limit exceeded)"
            else:
                error_message += " (Authentication failed or forbidden)"
        elif status == 404:
            error_message += " (Repository not found or private without access)"
        elif status == 422:
            error_message += " (Validation failed)"
        elif status == 429:
            error_message += " (Too many requests)"

        logger.error(error_message)
        raise GitHubAPIError(error_message) from error

    # --- Convenience Methods ---

    def fetch_commits(self, source: GitHubRepository, per_page: int = 30) -> list[dict]:
        """Fetch recent commits for the repository."""
        return self.fetch_json(source, "commits", params={"per_page": per_page})

    def fetch_issues(self, source: GitHubRepository, per_page: int = 30) -> list[dict]:
        """Fetch issues (including pull requests) for the repository."""
        return self.fetch_json(source, "issues", params={"state": "all", "per_page": per_page})

    # --- Discovery Methods (thêm vào GitHubFetcher class) ---

    def fetch_trending_repos(self, language: str = "python", since: str = "weekly") -> list[dict]:
        """Fetch trending repositories from GitHub Search API.

        Uses GitHub Search API to find trending repos based on stars gained
        in a given time period. This is a workaround since GitHub doesn't
        expose the /trending page via API.

        Args:
            language: Programming language to filter by (e.g., "python").
            since: Time period: "daily", "weekly", "monthly".

        Returns:
            List of repository search result dictionaries.
        """
        # Calculate date threshold based on 'since'
        from datetime import datetime, timedelta, timezone

        now = datetime.now(timezone.utc)
        if since == "daily":
            threshold = now - timedelta(days=1)
            min_stars = 50
        elif since == "weekly":
            threshold = now - timedelta(weeks=1)
            min_stars = 100
        else:  # monthly
            threshold = now - timedelta(days=30)
            min_stars = 500

        date_str = threshold.strftime("%Y-%m-%d")
        query = f"language:{language} created:>{date_str} stars:>={min_stars}"

        logger.info(
            "Fetching trending repos: language=%s, since=%s, query='%s'",
            language,
            since,
            query,
        )

        return self._search_repositories(query, sort="stars", order="desc", per_page=30)

    def fetch_new_repos_by_topic(
        self, topic: str, min_stars: int = 20, per_page: int = 20
    ) -> list[dict]:
        """Fetch newly created repositories matching a specific topic.

        Args:
            topic: GitHub topic to search (e.g., "llm", "agents", "rag").
            min_stars: Minimum star count to filter results.
            per_page: Number of results per page.

        Returns:
            List of repository search result dictionaries.
        """
        from datetime import datetime, timedelta, timezone

        # Search repos created in the last 30 days with the given topic
        threshold = datetime.now(timezone.utc) - timedelta(days=30)
        date_str = threshold.strftime("%Y-%m-%d")
        query = f"topic:{topic} created:>{date_str} stars:>={min_stars}"

        logger.info(
            "Fetching new repos by topic: topic=%s, min_stars=%d, query='%s'",
            topic,
            min_stars,
            query,
        )

        return self._search_repositories(query, sort="stars", order="desc", per_page=per_page)

    def _search_repositories(
        self, query: str, sort: str = "stars", order: str = "desc", per_page: int = 30
    ) -> list[dict]:
        """Internal helper to call GitHub Search API for repositories.

        Args:
            query: Search query string.
            sort: Sort field ("stars", "updated", "created").
            order: Sort order ("asc" or "desc").
            per_page: Number of results per page (max 100).

        Returns:
            List of repository dictionaries from search results.
        """
        url = f"{self.BASE_URL}/search/repositories"
        params: dict[str, str | int] = {
            "q": query,
            "sort": sort,
            "order": order,
            "per_page": min(per_page, 100),
        }

        logger.info("GitHub Search API: query='%s', sort=%s", query, sort)

        try:
            response = httpx.get(url, headers=self._headers, timeout=self._timeout, params=params)
            response.raise_for_status()
            data: dict = response.json()
            items: list[dict] = data.get("items", [])
            logger.info("GitHub Search returned %d results", len(items))
            return items

        except httpx.TimeoutException as error:
            logger.error("Timeout while searching GitHub: %s", error)
            raise FetchTimeoutError(f"Timeout searching GitHub: {query}") from error

        except httpx.HTTPStatusError as error:
            status = error.response.status_code
            self._handle_http_error(status, url, error)

        except httpx.RequestError as error:
            logger.error("Network error while searching GitHub: %s", error)
            raise NetworkError("Network error searching GitHub") from error

        return []
