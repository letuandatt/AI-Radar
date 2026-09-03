"""Tests for GitHub Parser implementation."""

import logging
from datetime import datetime

import pytest

from app.fetchers.github_parser import GitHubParser
from app.models.source import GitHubRepository


@pytest.fixture
def parser():
    """Provide a GitHubParser instance."""
    return GitHubParser()


@pytest.fixture
def mock_repo():
    """Provide a mock GitHub repository."""
    return GitHubRepository(name="test_repo", owner="test_owner", repo="test_repo_name")


# --- Sample JSON Data ---

SAMPLE_COMMITS = [
    {
        "sha": "abc123",
        "html_url": "https://github.com/test_owner/test_repo/commit/abc123",
        "commit": {
            "message": "Initial commit\n\nThis is the first commit",
            "author": {"date": "2023-10-25T10:00:00Z"},
        },
    },
    {
        "sha": "def456",
        "html_url": "https://github.com/test_owner/test_repo/commit/def456",
        "commit": {"message": "Fix bug in parser", "author": {"date": "2023-10-26T15:30:00+00:00"}},
    },
]

SAMPLE_ISSUES = [
    {
        "number": 1,
        "title": "Bug: Parser fails on empty input",
        "html_url": "https://github.com/test_owner/test_repo/issues/1",
        "body": "When input is empty, the parser crashes.\n\n"
        "Steps to reproduce:\n1. Pass empty string",
        "created_at": "2023-10-20T08:00:00Z",
    },
    {
        "number": 2,
        "title": "Feature: Add support for Atom feeds",
        "html_url": "https://github.com/test_owner/test_repo/issues/2",
        "body": None,  # Body can be None
        "created_at": "2023-10-21T09:30:00Z",
    },
]

INVALID_COMMIT = {
    "sha": "invalid",
    "html_url": "https://github.com/test_owner/test_repo/commit/invalid",
    # Missing "commit" key
}

INVALID_ISSUE = {
    "number": 99,
    # Missing "title"
    "html_url": "https://github.com/test_owner/test_repo/issues/99",
    "body": "Some content",
}


# --- Tests for parse_commits ---


def test_parse_commits_success(parser, mock_repo):
    """Verify that valid commit JSON is parsed into correct RawArticle models."""
    articles = parser.parse_commits(SAMPLE_COMMITS, mock_repo)

    assert len(articles) == 2

    # Check first commit
    assert articles[0].title == "Initial commit"
    assert articles[0].url == "https://github.com/test_owner/test_repo/commit/abc123"
    assert "This is the first commit" in articles[0].content
    assert articles[0].source_name == "test_repo"
    assert isinstance(articles[0].published_date, datetime)

    # Check second commit
    assert articles[1].title == "Fix bug in parser"
    assert articles[1].published_date is not None


def test_parse_commits_skips_invalid_entries(parser, mock_repo, caplog):
    """Verify that commits missing required fields are skipped and logged."""
    invalid_data = [INVALID_COMMIT, SAMPLE_COMMITS[0]]

    with caplog.at_level(logging.WARNING):
        articles = parser.parse_commits(invalid_data, mock_repo)

    assert len(articles) == 1
    assert articles[0].title == "Initial commit"
    assert "Skipping invalid commit" in caplog.text


def test_parse_commits_skips_empty_message(parser, mock_repo, caplog):
    """Verify that commits with empty message are skipped."""
    empty_message_commit = {
        "sha": "empty",
        "html_url": "https://github.com/test_owner/test_repo/commit/empty",
        "commit": {"message": "", "author": {"date": "2023-10-25T10:00:00Z"}},
    }

    with caplog.at_level(logging.WARNING):
        articles = parser.parse_commits([empty_message_commit], mock_repo)

    assert len(articles) == 0
    assert "Skipping commit" in caplog.text


# --- Tests for parse_issues ---


def test_parse_issues_success(parser, mock_repo):
    """Verify that valid issue JSON is parsed into correct RawArticle models."""
    articles = parser.parse_issues(SAMPLE_ISSUES, mock_repo)

    assert len(articles) == 2

    # Check first issue
    assert articles[0].title == "Bug: Parser fails on empty input"
    assert articles[0].url == "https://github.com/test_owner/test_repo/issues/1"
    assert "Steps to reproduce" in articles[0].content
    assert articles[0].source_name == "test_repo"
    assert isinstance(articles[0].published_date, datetime)

    # Check second issue (with None body)
    assert articles[1].title == "Feature: Add support for Atom feeds"
    assert articles[1].content == ""  # None should be converted to empty string


def test_parse_issues_skips_invalid_entries(parser, mock_repo, caplog):
    """Verify that issues missing required fields are skipped and logged."""
    invalid_data = [INVALID_ISSUE, SAMPLE_ISSUES[0]]

    with caplog.at_level(logging.WARNING):
        articles = parser.parse_issues(invalid_data, mock_repo)

    assert len(articles) == 1
    assert articles[0].title == "Bug: Parser fails on empty input"
    assert "Skipping invalid issue" in caplog.text


# --- Tests for date parsing ---


def test_parse_iso_date_with_z_suffix(parser):
    """Verify that ISO dates with 'Z' suffix are parsed correctly."""
    date_str = "2023-10-25T10:00:00Z"
    result = parser._parse_iso_date(date_str)

    assert result is not None
    assert result.year == 2023
    assert result.month == 10
    assert result.day == 25
    assert result.hour == 10


def test_parse_iso_date_with_timezone(parser):
    """Verify that ISO dates with timezone offset are parsed correctly."""
    date_str = "2023-10-25T10:00:00+00:00"
    result = parser._parse_iso_date(date_str)

    assert result is not None
    assert result.tzinfo is not None


def test_parse_iso_date_invalid_format(parser, caplog):
    """Verify that invalid date strings return None and log warning."""
    with caplog.at_level(logging.WARNING):
        result = parser._parse_iso_date("not-a-date")

    assert result is None
    assert "Failed to parse date" in caplog.text


def test_parse_iso_date_none(parser):
    """Verify that None input returns None."""
    result = parser._parse_iso_date(None)
    assert result is None


# --- Tests for source mapping ---


def test_parse_commits_maps_source_name(parser, mock_repo):
    """Verify that source_name is correctly mapped from repository."""
    articles = parser.parse_commits(SAMPLE_COMMITS, mock_repo)

    for article in articles:
        assert article.source_name == "test_repo"


def test_parse_issues_maps_source_name(parser, mock_repo):
    """Verify that source_name is correctly mapped from repository."""
    articles = parser.parse_issues(SAMPLE_ISSUES, mock_repo)

    for article in articles:
        assert article.source_name == "test_repo"
