"""Tests for Source Configuration Service."""

from unittest.mock import MagicMock, patch

import pytest

from app.models.source import GitHubRepository, HFSource, HFSourceType, RSSSource
from app.models.validation import ValidationResult
from app.services.source_config_service import SourceConfigService


@pytest.fixture
def mock_registries():
    """Provide mock registries for testing."""
    rss_registry = MagicMock()
    github_registry = MagicMock()
    hf_registry = MagicMock()
    return rss_registry, github_registry, hf_registry


@pytest.fixture
def service(mock_registries):
    """Provide a SourceConfigService instance with mock registries."""
    rss_registry, github_registry, hf_registry = mock_registries
    return SourceConfigService(rss_registry, github_registry, hf_registry)


# ==============================================================================
# Update Source Tests
# ==============================================================================


class TestUpdateSource:
    """Tests for update_source method."""

    def test_update_rss_source_success(self, service, mock_registries):
        """Verify that a valid RSS source is updated successfully."""
        rss_registry, _, _ = mock_registries

        # Mock the validator instance method (not the class)
        with patch.object(service, "_rss_validator") as mock_validator:
            mock_validator.validate.return_value = ValidationResult.success()

            config = {"url": "https://example.com/feed"}
            result = service.update_source("rss", "test_feed", config)

            assert result.is_valid is True
            rss_registry.register.assert_called_once()

            # Verify the registered source
            registered_source = rss_registry.register.call_args[0][0]
            assert isinstance(registered_source, RSSSource)
            assert registered_source.name == "test_feed"
            assert registered_source.url == "https://example.com/feed"

    def test_update_github_source_success(self, service, mock_registries):
        """Verify that a valid GitHub source is updated successfully."""
        _, github_registry, _ = mock_registries

        with patch.object(service, "_github_validator") as mock_validator:
            mock_validator.validate.return_value = ValidationResult.success()

            config = {"owner": "tiangolo", "repo": "fastapi"}
            result = service.update_source("github", "fastapi_repo", config)

            assert result.is_valid is True
            github_registry.register.assert_called_once()

            registered_source = github_registry.register.call_args[0][0]
            assert isinstance(registered_source, GitHubRepository)
            assert registered_source.owner == "tiangolo"
            assert registered_source.repo == "fastapi"

    def test_update_huggingface_source_success(self, service, mock_registries):
        """Verify that a valid HuggingFace source is updated successfully."""
        _, _, hf_registry = mock_registries

        with patch.object(service, "_hf_validator") as mock_validator:
            mock_validator.validate.return_value = ValidationResult.success()

            config = {"resource_id": "google-bert/bert-base-uncased", "source_type": "model"}
            result = service.update_source("huggingface", "bert_model", config)

            assert result.is_valid is True
            hf_registry.register.assert_called_once()

            registered_source = hf_registry.register.call_args[0][0]
            assert isinstance(registered_source, HFSource)
            assert registered_source.resource_id == "google-bert/bert-base-uncased"
            assert registered_source.source_type == HFSourceType.MODEL

    def test_update_source_validation_failure(self, service, mock_registries):
        """Verify that source is NOT registered when validation fails."""
        rss_registry, _, _ = mock_registries

        with patch.object(service, "_rss_validator") as mock_validator:
            mock_validator.validate.return_value = ValidationResult.failure(
                error_message="URL not accessible",
                details={"url": "https://invalid.com/feed"},
            )

            config = {"url": "https://invalid.com/feed"}
            result = service.update_source("rss", "test_feed", config)

            assert result.is_valid is False
            assert "URL not accessible" in result.error_message
            rss_registry.register.assert_not_called()

    def test_update_source_unknown_type(self, service):
        """Verify that unknown source type returns failure."""
        config = {"url": "https://example.com"}
        result = service.update_source("unknown", "test", config)

        assert result.is_valid is False
        assert "Unknown source type" in result.error_message

    def test_update_source_missing_required_field(self, service):
        """Verify that missing required field returns validation failure."""
        # RSSSource requires 'url' field
        config = {}  # Missing 'url'

        # Service catches Pydantic ValidationError and returns failure
        result = service.update_source("rss", "test_feed", config)

        assert result.is_valid is False
        # Error message should mention the missing field or validation failure
        assert "url" in result.error_message.lower() or "validation" in result.error_message.lower()


# ==============================================================================
# Get Source Config Tests
# ==============================================================================


class TestGetSourceConfig:
    """Tests for get_source_config method."""

    def test_get_rss_source_config(self, service, mock_registries):
        """Verify that RSS source config is retrieved correctly."""
        rss_registry, _, _ = mock_registries

        mock_source = RSSSource(name="test", url="https://example.com/feed")
        rss_registry.get_by_name.return_value = mock_source

        result = service.get_source_config("rss", "test")

        assert result is not None
        assert result["name"] == "test"
        assert result["url"] == "https://example.com/feed"

    def test_get_source_config_not_found(self, service, mock_registries):
        """Verify that None is returned when source is not found."""
        rss_registry, _, _ = mock_registries
        rss_registry.get_by_name.side_effect = KeyError("Source not found")

        result = service.get_source_config("rss", "nonexistent")

        assert result is None

    def test_get_source_config_unknown_type(self, service):
        """Verify that None is returned for unknown source type."""
        result = service.get_source_config("unknown", "test")

        assert result is None


# ==============================================================================
# Remove Source Tests
# ==============================================================================


class TestRemoveSource:
    """Tests for remove_source method."""

    def test_remove_source_not_supported(self, service, mock_registries):
        """Verify that remove returns False (not yet supported)."""
        rss_registry, _, _ = mock_registries

        # Mock source exists
        mock_source = RSSSource(name="test", url="https://example.com/feed")
        rss_registry.get_by_name.return_value = mock_source

        result = service.remove_source("rss", "test")

        # Currently returns False because registry doesn't support removal
        assert result is False


# ==============================================================================
# Get Source Schema Tests
# ==============================================================================


class TestGetSourceSchema:
    """Tests for get_source_schema method."""

    def test_get_rss_schema(self, service):
        """Verify that RSS schema is returned correctly."""
        schema = service.get_source_schema("rss")

        assert schema is not None
        assert "properties" in schema
        assert "name" in schema["properties"]
        assert "url" in schema["properties"]
        assert "is_active" in schema["properties"]

    def test_get_github_schema(self, service):
        """Verify that GitHub schema is returned correctly."""
        schema = service.get_source_schema("github")

        assert schema is not None
        assert "properties" in schema
        assert "name" in schema["properties"]
        assert "owner" in schema["properties"]
        assert "repo" in schema["properties"]

    def test_get_huggingface_schema(self, service):
        """Verify that HuggingFace schema is returned correctly."""
        schema = service.get_source_schema("huggingface")

        assert schema is not None
        assert "properties" in schema
        assert "name" in schema["properties"]
        assert "resource_id" in schema["properties"]
        assert "source_type" in schema["properties"]

    def test_get_schema_unknown_type(self, service):
        """Verify that None is returned for unknown source type."""
        schema = service.get_source_schema("unknown")

        assert schema is None


# ==============================================================================
# Get All Source Types Tests
# ==============================================================================


class TestGetAllSourceTypes:
    """Tests for get_all_source_types method."""

    def test_get_all_source_types(self, service):
        """Verify that all source types are returned."""
        types = service.get_all_source_types()

        assert types == ["rss", "github", "huggingface"]
