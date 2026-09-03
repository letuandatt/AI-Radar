"""GitHub Data Parser implementation.

This module provides the concrete implementation of the Parser protocol
for transforming raw GitHub content into structured RawArticle models.
"""

from datetime import datetime

from app.core.logger import get_logger
from app.models.article import RawArticle
from app.models.source import GitHubRepository

logger = get_logger(__name__)


class GitHubParser:
    """Parses JSON data from GitHub API into RawArticle models.

    This parser handles the specific JSON structures returned by the
    GitHub REST API for commits and issues, transforming them into
    the standardized RawArticle format.
    """

    def parse_commits(self, data: list[dict], source: GitHubRepository) -> list[RawArticle]:
        """Parse a list of commit JSON objects into RawArticle models.

        Args:
            data: List of commit dictionaries from GitHub API.
            source: The source repository these commits belong to.

        Returns:
            A list of parsed RawArticle instances.
        """
        articles: list[RawArticle] = []

        for item in data:
            commit_data = item.get("commit")
            html_url = item.get("html_url")

            # Defensive Parsing: Skip if essential data is missing
            if not commit_data or not html_url:
                logger.warning(
                    "Skipping invalid commit from %s: missing commit data or html_url", source.name
                )
                continue

            message = commit_data.get("message", "")
            if not message:
                logger.warning(
                    "Skipping commit from %s with empty message: %s", source.name, html_url
                )
                continue

            # Extract title (first line of commit message) and full content
            title = message.split("\n")[0].strip()
            content = message

            # Extract date from nested author object
            author_data = commit_data.get("author") or {}
            published_date = self._parse_iso_date(author_data.get("date"))

            articles.append(
                RawArticle(
                    title=title,
                    url=html_url,
                    content=content,
                    published_date=published_date,
                    source_name=source.name,
                )
            )

        logger.info("Parsed %d commits from %s", len(articles), source.name)
        return articles

    def parse_issues(self, data: list[dict], source: GitHubRepository) -> list[RawArticle]:
        """Parse a list of issue JSON objects into RawArticle models.

        Args:
            data: List of issue dictionaries from GitHub API.
            source: The source repository these issues belong to.

        Returns:
            A list of parsed RawArticle instances.
        """
        articles: list[RawArticle] = []

        for item in data:
            title = item.get("title")
            html_url = item.get("html_url")

            # Defensive Parsing: Skip if essential data is missing
            if not title or not html_url:
                logger.warning(
                    "Skipping invalid issue from %s: missing title or html_url", source.name
                )
                continue

            # Body can be None or empty string
            content = item.get("body") or ""
            published_date = self._parse_iso_date(item.get("created_at"))

            articles.append(
                RawArticle(
                    title=title,
                    url=html_url,
                    content=content,
                    published_date=published_date,
                    source_name=source.name,
                )
            )

        logger.info("Parsed %d issues from %s", len(articles), source.name)
        return articles

    def _parse_iso_date(self, date_str: str | None) -> datetime | None:
        """Convert GitHub's ISO 8601 date string to a datetime object.

        GitHub returns dates like "2023-10-25T10:00:00Z".
        Python's fromisoformat() doesn't handle the 'Z' suffix until Python 3.11,
        so we replace it with '+00:00' for compatibility.
        """
        if not date_str:
            return None
        try:
            if date_str.endswith("Z"):
                date_str = date_str[:-1] + "+00:00"
            return datetime.fromisoformat(date_str)
        except ValueError as error:
            logger.warning("Failed to parse date '%s': %s", date_str, error)
            return None

    def parse_search_results(
        self, data: list[dict], source_name: str = "github-discovery"
    ) -> list[RawArticle]:
        """Parse GitHub search results into RawArticle models.

        Args:
            data: List of repository dictionaries from GitHub Search API.
            source_name: Name to use for source_name field.

        Returns:
            List of parsed RawArticle instances.
        """
        articles: list[RawArticle] = []

        for repo in data:
            full_name = repo.get("full_name")
            html_url = repo.get("html_url")
            description = repo.get("description") or ""

            if not full_name or not html_url:
                logger.warning(
                    "Skipping invalid search result from %s: missing full_name or html_url",
                    source_name,
                )
                continue

            # Build title from full_name and description
            title = full_name
            if description:
                title = f"{full_name}: {description[:80]}"

            # Build content with repo metadata
            stars = repo.get("stargazers_count", 0)
            forks = repo.get("forks_count", 0)
            language = repo.get("language", "Unknown")
            topics = repo.get("topics", [])

            content_parts = [
                f"Repository: {full_name}",
                f"URL: {html_url}",
                f"Description: {description}",
                f"Stars: {stars}",
                f"Forks: {forks}",
                f"Language: {language}",
            ]
            if topics:
                content_parts.append(f"Topics: {', '.join(topics[:10])}")

            content = "\n".join(content_parts)

            # Parse creation date
            published_date = self._parse_iso_date(repo.get("created_at"))

            articles.append(
                RawArticle(
                    title=title,
                    url=html_url,
                    content=content,
                    published_date=published_date,
                    source_name=source_name,
                )
            )

        logger.info("Parsed %d search results from %s", len(articles), source_name)
        return articles
