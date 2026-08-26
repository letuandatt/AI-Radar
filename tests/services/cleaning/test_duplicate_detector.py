"""Tests for Duplicate Data Detection Service."""

from datetime import datetime

import pytest

from app.core.utils import compute_content_hash, normalize_title, normalize_url
from app.models.article import RawArticle
from app.services.cleaning.duplicate_detector import DuplicateDetector


@pytest.fixture
def detector():
    """Provide a DuplicateDetector instance."""
    return DuplicateDetector()


def create_article(url: str, title: str, content: str = "Some content") -> RawArticle:
    """Helper to create a RawArticle for testing."""
    return RawArticle(
        title=title,
        url=url,
        content=content,
        source_name="test_source",
        published_date=datetime.now(),
    )


# ==============================================================================
# Utility Function Tests
# ==============================================================================


class TestNormalizeUrl:
    """Tests for URL normalization."""

    def test_normalize_trailing_slash(self):
        assert normalize_url("https://example.com/article/") == "https://example.com/article"

    def test_normalize_case_insensitive(self):
        assert normalize_url("HTTPS://EXAMPLE.COM/Article") == "https://example.com/Article"

    def test_normalize_remove_fragment(self):
        assert normalize_url("https://example.com/article#section") == "https://example.com/article"

    def test_normalize_whitespace(self):
        assert normalize_url("  https://example.com/article  ") == "https://example.com/article"


class TestNormalizeTitle:
    """Tests for title normalization."""

    def test_normalize_lowercase(self):
        assert normalize_title("BREAKING NEWS") == "breaking news"

    def test_normalize_collapse_whitespace(self):
        assert normalize_title("Breaking   News   Today") == "breaking news today"

    def test_normalize_strip_whitespace(self):
        assert normalize_title("  Breaking News  ") == "breaking news"


class TestComputeContentHash:
    """Tests for content hash computation."""

    def test_same_content_same_hash(self):
        hash1 = compute_content_hash("https://example.com/article", "Breaking News")
        hash2 = compute_content_hash("https://example.com/article", "Breaking News")
        assert hash1 == hash2

    def test_normalized_variants_same_hash(self):
        hash1 = compute_content_hash("https://example.com/article/", "  BREAKING   NEWS  ")
        hash2 = compute_content_hash("https://example.com/article", "breaking news")
        assert hash1 == hash2

    def test_different_url_different_hash(self):
        hash1 = compute_content_hash("https://example.com/article1", "News")
        hash2 = compute_content_hash("https://example.com/article2", "News")
        assert hash1 != hash2

    def test_different_title_different_hash(self):
        hash1 = compute_content_hash("https://example.com/article", "News 1")
        hash2 = compute_content_hash("https://example.com/article", "News 2")
        assert hash1 != hash2


# ==============================================================================
# DuplicateDetector Tests
# ==============================================================================


class TestDuplicateDetector:
    """Tests for DuplicateDetector."""

    def test_deduplicate_empty_list(self, detector):
        result = detector.deduplicate([])
        assert result == []

    def test_deduplicate_all_unique(self, detector):
        articles = [
            create_article("https://example.com/1", "Article One Title"),
            create_article("https://example.com/2", "Article Two Title"),
            create_article("https://example.com/3", "Article Three Title"),
        ]
        result = detector.deduplicate(articles)
        assert len(result) == 3

    def test_deduplicate_exact_duplicates(self, detector):
        articles = [
            create_article("https://example.com/article", "Breaking News Today"),
            create_article("https://example.com/article", "Breaking News Today"),
            create_article("https://example.com/article", "Breaking News Today"),
        ]
        result = detector.deduplicate(articles)
        assert len(result) == 1

    def test_deduplicate_normalized_duplicates(self, detector):
        """Verify that normalized variants are detected as duplicates."""
        articles = [
            create_article("https://example.com/article/", "  BREAKING   NEWS  "),
            create_article("https://example.com/article", "breaking news"),
            create_article("HTTPS://EXAMPLE.COM/article", "Breaking News"),
        ]
        result = detector.deduplicate(articles)
        assert len(result) == 1

    def test_deduplicate_same_url_different_title(self, detector):
        articles = [
            create_article("https://example.com/article", "Title One"),
            create_article("https://example.com/article", "Title Two"),
        ]
        result = detector.deduplicate(articles)
        assert len(result) == 2

    def test_deduplicate_different_url_same_title(self, detector):
        articles = [
            create_article("https://example.com/article1", "Same Title"),
            create_article("https://example.com/article2", "Same Title"),
        ]
        result = detector.deduplicate(articles)
        assert len(result) == 2

    def test_deduplicate_keeps_first_occurrence(self, detector):
        """Verify that the first occurrence is kept, not the last."""
        articles = [
            create_article("https://example.com/article", "Breaking News Today"),
            create_article("https://example.com/article", "Breaking News Today"),
            create_article("https://example.com/article", "Breaking News Today"),
        ]

        result = detector.deduplicate(articles)

        assert len(result) == 1
        assert result[0].title == "Breaking News Today"

    def test_deduplicate_preserves_order(self, detector):
        """Verify that the order of unique articles is preserved."""
        articles = [
            create_article("https://example.com/1", "Article One"),
            create_article("https://example.com/2", "Article Two"),
            create_article("https://example.com/1", "Article One"),  # Cùng title
            create_article("https://example.com/3", "Article Three"),
            create_article("https://example.com/2", "Article Two"),  # Cùng title
        ]

        result = detector.deduplicate(articles)

        assert len(result) == 3
        assert result[0].url == "https://example.com/1"
        assert result[1].url == "https://example.com/2"
        assert result[2].url == "https://example.com/3"

    def test_deduplicate_does_not_modify_input(self, detector):
        articles = [
            create_article("https://example.com/article", "Title"),
            create_article("https://example.com/article", "Title"),
        ]
        original_length = len(articles)
        detector.deduplicate(articles)
        assert len(articles) == original_length


# ==============================================================================
# Logging Tests
# ==============================================================================


class TestDuplicateDetectorLogging:
    """Tests for logging behavior."""

    def test_deduplicate_logs_duplicates(self, detector, caplog):
        articles = [
            create_article("https://example.com/article", "Breaking News"),
            create_article("https://example.com/article", "Breaking News"),
        ]
        with caplog.at_level("INFO"):
            detector.deduplicate(articles)

        log_messages = [record.message for record in caplog.records]
        duplicate_logs = [msg for msg in log_messages if "Duplicate detected" in msg]
        assert len(duplicate_logs) == 1

    def test_deduplicate_logs_summary(self, detector, caplog):
        """Verify that summary log is generated."""
        articles = [
            create_article("https://example.com/1", "Article One"),
            create_article("https://example.com/1", "Article One"),  # Cùng title
            create_article("https://example.com/2", "Article Two"),
        ]

        with caplog.at_level("INFO"):
            detector.deduplicate(articles)

        log_messages = [record.message for record in caplog.records]
        summary_logs = [msg for msg in log_messages if "DuplicateDetector completed" in msg]

        assert len(summary_logs) == 1
        assert "2 unique" in summary_logs[0]
        assert "1 duplicates removed" in summary_logs[0]
        assert "3 total" in summary_logs[0]
