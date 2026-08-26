"""Tests for Source Validation Service."""

from unittest.mock import MagicMock, patch

import httpx

from app.models.source import GitHubRepository, HFSource, HFSourceType, RSSSource
from app.services.source_validator import (
    GitHubValidator,
    HuggingFaceValidator,
    RSSValidator,
)

# ==============================================================================
# RSS Validator Tests
# ==============================================================================


class TestRSSValidator:
    """Tests for RSSValidator."""

    @patch("app.services.source_validator.httpx.head")
    def test_validate_success(self, mock_head):
        """Verify that a valid RSS feed returns success."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "application/rss+xml"}
        mock_head.return_value = mock_response

        validator = RSSValidator(timeout=5.0)
        source = RSSSource(name="test", url="https://example.com/feed")

        result = validator.validate(source)

        assert result.is_valid is True
        assert result.error_message is None
        assert "application/rss+xml" in result.details.get("content_type", "")

    @patch("app.services.source_validator.httpx.head")
    def test_validate_404(self, mock_head):
        """Verify that a 404 response returns failure."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_head.return_value = mock_response

        validator = RSSValidator()
        source = RSSSource(name="test", url="https://example.com/feed")

        result = validator.validate(source)

        assert result.is_valid is False
        assert "404" in result.error_message

    @patch("app.services.source_validator.httpx.head")
    def test_validate_invalid_content_type(self, mock_head):
        """Verify that invalid content-type returns failure."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "text/html"}
        mock_head.return_value = mock_response

        validator = RSSValidator()
        source = RSSSource(name="test", url="https://example.com/feed")

        result = validator.validate(source)

        assert result.is_valid is False
        assert "content-type" in result.error_message.lower()

    @patch("app.services.source_validator.httpx.head")
    def test_validate_timeout(self, mock_head):
        """Verify that timeout returns failure without hanging."""
        mock_head.side_effect = httpx.TimeoutException("Timeout")

        validator = RSSValidator(timeout=1.0)
        source = RSSSource(name="test", url="https://example.com/feed")

        result = validator.validate(source)

        assert result.is_valid is False
        assert "timeout" in result.error_message.lower()

    @patch("app.services.source_validator.httpx.head")
    def test_validate_network_error(self, mock_head):
        """Verify that network error returns failure."""
        mock_head.side_effect = httpx.ConnectError("Connection refused")

        validator = RSSValidator()
        source = RSSSource(name="test", url="https://example.com/feed")

        result = validator.validate(source)

        assert result.is_valid is False
        assert "network error" in result.error_message.lower()


# ==============================================================================
# GitHub Validator Tests
# ==============================================================================


class TestGitHubValidator:
    """Tests for GitHubValidator."""

    @patch("app.services.source_validator.httpx.get")
    def test_validate_success(self, mock_get):
        """Verify that an accessible repo returns success."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response

        validator = GitHubValidator()
        source = GitHubRepository(name="fastapi", owner="tiangolo", repo="fastapi")

        result = validator.validate(source)

        assert result.is_valid is True
        assert result.error_message is None

    @patch("app.services.source_validator.httpx.get")
    def test_validate_404(self, mock_get):
        """Verify that a non-existent repo returns failure."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response

        validator = GitHubValidator()
        source = GitHubRepository(name="test", owner="test", repo="nonexistent")

        result = validator.validate(source)

        assert result.is_valid is False
        assert "not found" in result.error_message.lower()

    @patch("app.services.source_validator.httpx.get")
    def test_validate_401(self, mock_get):
        """Verify that authentication failure returns failure."""
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_get.return_value = mock_response

        validator = GitHubValidator()
        source = GitHubRepository(name="test", owner="test", repo="private")

        result = validator.validate(source)

        assert result.is_valid is False
        assert "authentication" in result.error_message.lower()

    @patch("app.services.source_validator.httpx.get")
    def test_validate_with_token(self, mock_get):
        """Verify that token is included in headers when provided."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response

        validator = GitHubValidator(token="test_token")
        source = GitHubRepository(name="test", owner="test", repo="repo")

        validator.validate(source)

        # Verify token was passed in headers
        call_kwargs = mock_get.call_args.kwargs
        assert "Authorization" in call_kwargs["headers"]
        assert "test_token" in call_kwargs["headers"]["Authorization"]

    @patch("app.services.source_validator.httpx.get")
    def test_validate_timeout(self, mock_get):
        """Verify that timeout returns failure."""
        mock_get.side_effect = httpx.TimeoutException("Timeout")

        validator = GitHubValidator(timeout=1.0)
        source = GitHubRepository(name="test", owner="test", repo="repo")

        result = validator.validate(source)

        assert result.is_valid is False
        assert "timeout" in result.error_message.lower()


# ==============================================================================
# HuggingFace Validator Tests
# ==============================================================================


class TestHuggingFaceValidator:
    """Tests for HuggingFaceValidator."""

    @patch("app.services.source_validator.httpx.get")
    def test_validate_dataset_success(self, mock_get):
        """Verify that an accessible dataset returns success."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response

        validator = HuggingFaceValidator()
        source = HFSource(
            name="squad",
            resource_id="rajpurkar/squad",
            source_type=HFSourceType.DATASET,
        )

        result = validator.validate(source)

        assert result.is_valid is True
        # Verify correct URL was called
        call_args = mock_get.call_args.args[0]
        assert "datasets/rajpurkar/squad" in call_args

    @patch("app.services.source_validator.httpx.get")
    def test_validate_model_success(self, mock_get):
        """Verify that an accessible model returns success."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response

        validator = HuggingFaceValidator()
        source = HFSource(
            name="bert",
            resource_id="google-bert/bert-base-uncased",
            source_type=HFSourceType.MODEL,
        )

        result = validator.validate(source)

        assert result.is_valid is True
        # Verify correct URL was called
        call_args = mock_get.call_args.args[0]
        assert "models/google-bert/bert-base-uncased" in call_args

    @patch("app.services.source_validator.httpx.get")
    def test_validate_404(self, mock_get):
        """Verify that a non-existent resource returns failure."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response

        validator = HuggingFaceValidator()
        source = HFSource(
            name="test",
            resource_id="test/nonexistent",
            source_type=HFSourceType.MODEL,
        )

        result = validator.validate(source)

        assert result.is_valid is False
        assert "not found" in result.error_message.lower()

    @patch("app.services.source_validator.httpx.get")
    def test_validate_with_token(self, mock_get):
        """Verify that token is included in headers when provided."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response

        validator = HuggingFaceValidator(token="hf_test_token")
        source = HFSource(
            name="test",
            resource_id="test/model",
            source_type=HFSourceType.MODEL,
        )

        validator.validate(source)

        # Verify token was passed in headers
        call_kwargs = mock_get.call_args.kwargs
        assert "Authorization" in call_kwargs["headers"]
        assert "hf_test_token" in call_kwargs["headers"]["Authorization"]

    @patch("app.services.source_validator.httpx.get")
    def test_validate_timeout(self, mock_get):
        """Verify that timeout returns failure."""
        mock_get.side_effect = httpx.TimeoutException("Timeout")

        validator = HuggingFaceValidator(timeout=1.0)
        source = HFSource(
            name="test",
            resource_id="test/model",
            source_type=HFSourceType.MODEL,
        )

        result = validator.validate(source)

        assert result.is_valid is False
        assert "timeout" in result.error_message.lower()
