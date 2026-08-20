"""RSS Data Parser implementation.

This module provides the concrete implementation of the Parser protocol
for transforming raw RSS XML content into structured RawArticle models.
"""

import time
from datetime import datetime

import feedparser  # type: ignore[import-untyped]

from app.core.logger import get_logger
from app.fetchers.exceptions import ParsingError
from app.models.article import RawArticle
from app.models.source import RSSSource

logger = get_logger(__name__)


class RSSParser:
    """Parses raw RSS XML content into a list of RawArticle models.

    This implementation uses the `feedparser` library to handle the
    complexities of RSS and Atom feed formats. It includes defensive
    mechanisms to skip invalid entries and handle malformed XML gracefully.
    """

    def parse(self, raw_data: str, source: RSSSource) -> list[RawArticle]:
        """Parse raw XML data into a list of RawArticle models.

        Args:
            raw_data: The raw XML string content of the RSS feed.
            source: The source from which the data was fetched.

        Returns:
            A list of parsed RawArticle instances.

        Raises:
            ParsingError: If the raw data is fundamentally malformed
                          and contains no valid entries.
        """
        logger.info("Parsing RSS feed for source: %s", source.name)

        feed = feedparser.parse(raw_data)

        # feedparser is extremely resilient. It sets 'bozo' to 1 if there are
        # parsing errors. If it's bozo and has no entries, it's a fatal parse error.
        if feed.bozo == 1 and not feed.entries:
            bozo_exception = feed.get("bozo_exception", "Unknown error")
            logger.error("Failed to parse RSS feed for %s: %s", source.name, bozo_exception)
            raise ParsingError(f"Malformed RSS feed for {source.name}: {bozo_exception}")

        articles: list[RawArticle] = []

        for entry in feed.entries:
            article = self._map_entry_to_article(entry, source)
            if article is not None:
                articles.append(article)

        logger.info(
            "Successfully parsed %d articles from source %s (skipped %d invalid entries).",
            len(articles),
            source.name,
            len(feed.entries) - len(articles),
        )

        return articles

    def _map_entry_to_article(
        self, entry: feedparser.FeedParserDict, source: RSSSource
    ) -> RawArticle | None:
        """Map a single feed entry to a RawArticle model.

        Returns None if the entry is missing required fields (title, url).
        """
        title = entry.get("title")
        url = entry.get("link")

        # Skip entries missing mandatory fields
        if not title or not url:
            logger.warning(
                "Skipping invalid RSS entry from %s: missing title or link. Entry ID: %s",
                source.name,
                entry.get("id", "unknown_id"),
            )
            return None

        # Extract content (summary or content block)
        content = entry.get("summary", "")
        if not content and "content" in entry and len(entry.content) > 0:
            content = entry.content[0].get("value", "")

        # Parse published date
        published_date = self._parse_date(entry.get("published_parsed"))

        return RawArticle(
            title=title,
            url=url,
            content=content,
            published_date=published_date,
            source_name=source.name,
        )

    def _parse_date(self, published_parsed: time.struct_time | None) -> datetime | None:
        """Convert feedparser's struct_time to a standard datetime object."""
        if published_parsed is None:
            return None
        try:
            # struct_time is a tuple-like object: (year, month, day, hour, minute, second, ...)
            return datetime(*published_parsed[:6])
        except Exception as error:
            logger.warning("Failed to parse date: %s", error)
            return None
