"""Tests for Source Status Service."""

from unittest.mock import MagicMock, patch

import pytest

from app.models.source import RSSSource
from app.models.validation import ValidationResult
from app.services.source_status_service import SourceStatusService
from app.storage.source_status import SourceStatusStorage


@pytest.fixture
def mock_storage():
    """Provide a mock storage instance."""
    return MagicMock(spec=SourceStatusStorage)


@pytest.fixture
def mock_registries():
    """Provide mock registries."""
    return MagicMock(), MagicMock(), MagicMock()


@pytest.fixture
def service(mock_storage, mock_registries):
    """Provide a SourceStatusService instance."""
    rss_reg, gh_reg, hf_reg = mock_registries
    return SourceStatusService(mock_storage, rss_reg, gh_reg, hf_reg)


class TestMarkInactive:
    """Tests for mark_inactive method."""

    def test_mark_inactive_saves_status(self, service, mock_storage):
        """Verify that mark_inactive saves the correct status."""
        service.mark_inactive("test_rss", "rss", "Network error")

        mock_storage.save_status.assert_called_once()
        saved_status = mock_storage.save_status.call_args[0][0]

        assert saved_status.source_name == "test_rss"
        assert saved_status.source_type == "rss"
        assert saved_status.is_active is False
        assert saved_status.error_message == "Network error"
        assert saved_status.last_checked is not None


class TestMarkActive:
    """Tests for mark_active method."""

    def test_mark_active_success(self, service, mock_storage, mock_registries):
        """Verify that mark_active succeeds when validation passes."""
        rss_reg, _, _ = mock_registries
        mock_source = RSSSource(name="test_rss", url="https://example.com/feed")
        rss_reg.get_by_name.return_value = mock_source

        # Patch the instance attribute directly to prevent real HTTP calls
        with patch.object(service, "_rss_validator") as mock_validator:
            mock_validator.validate.return_value = ValidationResult.success()

            result = service.mark_active("test_rss", "rss")

            assert result is True
            mock_storage.save_status.assert_called_once()
            saved_status = mock_storage.save_status.call_args[0][0]
            assert saved_status.is_active is True
            assert saved_status.error_message is None

    def test_mark_active_validation_failure(self, service, mock_storage, mock_registries):
        """Verify that mark_active fails and sets inactive when validation fails."""
        rss_reg, _, _ = mock_registries
        mock_source = RSSSource(name="test_rss", url="https://example.com/feed")
        rss_reg.get_by_name.return_value = mock_source

        # Patch the instance attribute directly to prevent real HTTP calls
        with patch.object(service, "_rss_validator") as mock_validator:
            mock_validator.validate.return_value = ValidationResult.failure("URL not accessible")

            result = service.mark_active("test_rss", "rss")

            assert result is False
            mock_storage.save_status.assert_called_once()
            saved_status = mock_storage.save_status.call_args[0][0]
            assert saved_status.is_active is False
            assert saved_status.error_message == "URL not accessible"

    def test_mark_active_source_not_found(self, service, mock_storage, mock_registries):
        """Verify that mark_active returns False if source is not in registry."""
        rss_reg, _, _ = mock_registries
        rss_reg.get_by_name.side_effect = KeyError("Not found")

        result = service.mark_active("nonexistent", "rss")

        assert result is False
        mock_storage.save_status.assert_not_called()

    def test_mark_active_unknown_source_type(self, service, mock_storage):
        """Verify that mark_active returns False for unknown source type."""
        result = service.mark_active("test", "unknown_type")

        assert result is False
        mock_storage.save_status.assert_not_called()


class TestGetStatus:
    """Tests for get_status and get_all_statuses methods."""

    def test_get_status(self, service, mock_storage):
        """Verify that get_status delegates to storage."""
        service.get_status("test_rss")
        mock_storage.get_status.assert_called_once_with("test_rss")

    def test_get_all_statuses(self, service, mock_storage):
        """Verify that get_all_statuses delegates to storage."""
        service.get_all_statuses()
        mock_storage.get_all_statuses.assert_called_once()
