"""Tests for RSS Parser implementation."""

import logging
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from app.fetchers.exceptions import ParsingError
from app.fetchers.rss_parser import RSSParser
from app.models.source import RSSSource


@pytest.fixture
def parser():
    """Provide an RSSParser instance."""
    return RSSParser()


@pytest.fixture
def mock_source():
    """Provide a mock RSS source."""
    return RSSSource(name="test_source", url="http://test.com/rss")


# --- Sample XML Data ---

VALID_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
    <channel>
        <title>Test Feed</title>
        <item>
            <title>Article 1</title>
            <link>http://test.com/1</link>
            <description>Content 1</description>
            <pubDate>Mon, 01 Jan 2024 12:00:00 GMT</pubDate>
        </item>
        <item>
            <title>Article 2</title>
            <link>http://test.com/2</link>
            <description>Content 2</description>
        </item>
    </channel>
</rss>"""

XML_WITH_INVALID_ENTRY = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
    <channel>
        <title>Test Feed</title>
        <item>
            <link>http://test.com/no-title</link>
            <description>Missing title</description>
        </item>
        <item>
            <title>Valid Article</title>
            <link>http://test.com/valid</link>
            <description>Valid content</description>
        </item>
    </channel>
</rss>"""


# --- Test Cases ---


def test_parse_success(parser, mock_source):
    """Verify that a valid RSS feed is parsed into correct RawArticle models."""
    articles = parser.parse(VALID_XML, mock_source)

    assert len(articles) == 2

    # Check first article (with date)
    assert articles[0].title == "Article 1"
    assert articles[0].url == "http://test.com/1"
    assert articles[0].content == "Content 1"
    assert articles[0].source_name == "test_source"
    assert isinstance(articles[0].published_date, datetime)

    # Check second article (without date)
    assert articles[1].title == "Article 2"
    assert articles[1].published_date is None


def test_parse_skips_invalid_entries(parser, mock_source, caplog):
    """Verify that entries missing required fields are skipped and logged."""
    with caplog.at_level(logging.WARNING):
        articles = parser.parse(XML_WITH_INVALID_ENTRY, mock_source)

    assert len(articles) == 1
    assert articles[0].title == "Valid Article"
    assert "Skipping invalid RSS entry" in caplog.text


def test_parse_raises_error_on_malformed_feed(parser, mock_source):
    """Verify that a fundamentally malformed feed raises ParsingError.

    Note: feedparser is extremely resilient. We mock it to simulate a fatal
    parse error where bozo=1 and no entries are found.
    """
    with patch("app.fetchers.rss_parser.feedparser.parse") as mock_parse:
        mock_feed = MagicMock()
        mock_feed.bozo = 1
        mock_feed.entries = []
        mock_feed.get.return_value = "Fatal XML syntax error"
        mock_parse.return_value = mock_feed

        with pytest.raises(ParsingError, match="Malformed RSS feed for test_source"):
            parser.parse("<invalid>xml", mock_source)


def test_parse_maps_source_name_correctly(parser, mock_source):
    """Verify that the source name is correctly mapped to all parsed articles."""
    articles = parser.parse(VALID_XML, mock_source)

    for article in articles:
        assert article.source_name == "test_source"
