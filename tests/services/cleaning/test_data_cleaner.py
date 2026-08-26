"""Tests for Invalid Data Removal Service."""

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from app.models.article import RawArticle
from app.models.validation import ValidationResult
from app.services.cleaning.data_cleaner import DataCleaner
from app.services.cleaning.raw_validator import RawDataValidator


@pytest.fixture
def mock_validator():
    """Provide a mock RawDataValidator."""
    return MagicMock(spec=RawDataValidator)


@pytest.fixture
def cleaner(mock_validator):
    """Provide a DataCleaner instance with mock validator."""
    return DataCleaner(validator=mock_validator)


@pytest.fixture
def valid_article():
    """Provide a valid RawArticle."""
    return RawArticle(
        title="This is a valid article title with enough length",
        url="https://example.com/valid-article",
        content="This is valid content with actual text.",
        source_name="test_source",
        published_date=datetime.now(),
    )


@pytest.fixture
def invalid_article():
    """Provide an invalid RawArticle (short title)."""
    return RawArticle(
        title="Short",
        url="https://example.com/invalid-article",
        content="Some content",
        source_name="test_source",
        published_date=datetime.now(),
    )


# ==============================================================================
# Basic Cleaning Tests
# ==============================================================================


class TestBasicCleaning:
    """Tests for basic cleaning functionality."""

    def test_clean_empty_list(self, cleaner, mock_validator):
        """Verify that cleaning an empty list returns empty list."""
        result = cleaner.clean([])

        assert result == []
        mock_validator.validate.assert_not_called()

    def test_clean_all_valid_articles(self, cleaner, mock_validator, valid_article):
        """Verify that all valid articles are kept."""
        mock_validator.validate.return_value = ValidationResult.success()

        articles = [valid_article, valid_article, valid_article]
        result = cleaner.clean(articles)

        assert len(result) == 3
        assert all(article.url == valid_article.url for article in result)

    def test_clean_all_invalid_articles(self, cleaner, mock_validator, invalid_article):
        """Verify that all invalid articles are removed."""
        mock_validator.validate.return_value = ValidationResult.failure(
            error_message="Title too short",
            details={"field": "title"},
        )

        articles = [invalid_article, invalid_article]
        result = cleaner.clean(articles)

        assert result == []

    def test_clean_mixed_articles(self, cleaner, mock_validator, valid_article, invalid_article):
        """Verify that only valid articles are kept in mixed list."""

        # Configure mock to return different results based on article
        def validate_side_effect(article):
            if article.url == valid_article.url:
                return ValidationResult.success()
            else:
                return ValidationResult.failure(
                    error_message="Title too short",
                    details={"field": "title"},
                )

        mock_validator.validate.side_effect = validate_side_effect

        articles = [valid_article, invalid_article, valid_article, invalid_article]
        result = cleaner.clean(articles)

        assert len(result) == 2
        assert all(article.url == valid_article.url for article in result)


# ==============================================================================
# Immutability Tests
# ==============================================================================


class TestImmutability:
    """Tests to verify input list is not modified."""

    def test_clean_does_not_modify_input(
        self, cleaner, mock_validator, valid_article, invalid_article
    ):
        """Verify that the input list is not modified."""
        mock_validator.validate.return_value = ValidationResult.success()

        articles = [valid_article, invalid_article]
        original_length = len(articles)

        cleaner.clean(articles)

        assert len(articles) == original_length
        assert articles[0] == valid_article
        assert articles[1] == invalid_article


# ==============================================================================
# Logging Tests
# ==============================================================================


class TestLogging:
    """Tests for logging behavior."""

    def test_clean_logs_removed_articles(
        self, cleaner, mock_validator, valid_article, invalid_article, caplog
    ):
        """Verify that removed articles are logged with reason."""

        def validate_side_effect(article):
            if article.url == valid_article.url:
                return ValidationResult.success()
            else:
                return ValidationResult.failure(
                    error_message="Title too short",
                    details={"field": "title", "actual_length": 5},
                )

        mock_validator.validate.side_effect = validate_side_effect

        articles = [valid_article, invalid_article]

        with caplog.at_level("INFO"):
            cleaner.clean(articles)

        # Check that removal was logged
        log_messages = [record.message for record in caplog.records]
        removal_logs = [msg for msg in log_messages if "Article removed" in msg]

        assert len(removal_logs) == 1
        assert invalid_article.url in removal_logs[0]
        assert "Title too short" in removal_logs[0]

    def test_clean_logs_summary(
        self, cleaner, mock_validator, valid_article, invalid_article, caplog
    ):
        """Verify that summary log is generated after cleaning."""

        def validate_side_effect(article):
            if article.url == valid_article.url:
                return ValidationResult.success()
            else:
                return ValidationResult.failure(error_message="Invalid")

        mock_validator.validate.side_effect = validate_side_effect

        articles = [valid_article, invalid_article, valid_article]

        with caplog.at_level("INFO"):
            cleaner.clean(articles)

        log_messages = [record.message for record in caplog.records]
        summary_logs = [msg for msg in log_messages if "DataCleaner completed" in msg]

        assert len(summary_logs) == 1
        assert "2 valid" in summary_logs[0]
        assert "1 removed" in summary_logs[0]
        assert "3 total" in summary_logs[0]


# ==============================================================================
# Validator Integration Tests
# ==============================================================================


class TestValidatorIntegration:
    """Tests for validator integration."""

    def test_validator_called_for_each_article(self, cleaner, mock_validator, valid_article):
        """Verify that validator is called once for each article."""
        mock_validator.validate.return_value = ValidationResult.success()

        articles = [valid_article, valid_article, valid_article]
        cleaner.clean(articles)

        assert mock_validator.validate.call_count == 3

    def test_validator_receives_correct_article(self, cleaner, mock_validator, valid_article):
        """Verify that validator receives the correct article instance."""
        mock_validator.validate.return_value = ValidationResult.success()

        cleaner.clean([valid_article])

        mock_validator.validate.assert_called_once_with(valid_article)
