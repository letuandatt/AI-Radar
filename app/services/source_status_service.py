"""Service for managing source operational status."""

from datetime import datetime

from app.core.logger import get_logger
from app.fetchers.registry import (
    ConfigBasedGitHubRegistry,
    ConfigBasedHFRegistry,
    ConfigBasedSourceRegistry,
)
from app.models.status import SourceStatus
from app.services.source_validator import (
    GitHubValidator,
    HuggingFaceValidator,
    RSSValidator,
)
from app.storage.source_status import SourceStatusStorage

logger = get_logger(__name__)


class SourceStatusService:
    """Service for managing the operational status of data sources.

    Handles marking sources as active/inactive and performs pre-flight
    validation before re-activating a source.
    """

    def __init__(
        self,
        storage: SourceStatusStorage,
        rss_registry: ConfigBasedSourceRegistry,
        github_registry: ConfigBasedGitHubRegistry,
        hf_registry: ConfigBasedHFRegistry,
    ) -> None:
        self._storage = storage
        self._rss_registry = rss_registry
        self._github_registry = github_registry
        self._hf_registry = hf_registry

        self._rss_validator = RSSValidator()
        self._github_validator = GitHubValidator()
        self._hf_validator = HuggingFaceValidator()

    def mark_inactive(self, source_name: str, source_type: str, error_message: str) -> None:
        """Mark a source as inactive due to an error."""
        logger.info("Marking source %s as inactive: %s", source_name, error_message)
        status = SourceStatus(
            source_name=source_name,
            source_type=source_type,
            is_active=False,
            last_checked=datetime.now(),
            error_message=error_message,
        )
        self._storage.save_status(status)

    def mark_active(self, source_name: str, source_type: str) -> bool:
        """Attempt to mark a source as active.

        This method performs a pre-flight validation of the source.
        If validation passes, the source is marked as active.
        If validation fails, the source remains (or is set to) inactive.

        Returns:
            True if the source was successfully marked as active, False otherwise.
        """
        logger.info("Attempting to mark source %s as active", source_name)

        # 1. Get source configuration from registry
        source = self._get_source_from_registry(source_name, source_type)
        if source is None:
            logger.warning("Source %s not found in registry. Cannot activate.", source_name)
            return False

        # 2. Validate source (Pre-flight)
        validator = self._get_validator(source_type)
        if validator is None:
            logger.error("No validator found for source type %s", source_type)
            return False

        validation_result = validator.validate(source)

        # 3. Update status based on validation
        if validation_result.is_valid:
            status = SourceStatus(
                source_name=source_name,
                source_type=source_type,
                is_active=True,
                last_checked=datetime.now(),
                error_message=None,
            )
            self._storage.save_status(status)
            logger.info("Source %s successfully marked as active", source_name)
            return True
        else:
            status = SourceStatus(
                source_name=source_name,
                source_type=source_type,
                is_active=False,
                last_checked=datetime.now(),
                error_message=validation_result.error_message or "Validation failed",
            )
            self._storage.save_status(status)
            logger.warning(
                "Source %s failed validation: %s", source_name, validation_result.error_message
            )
            return False

    def get_status(self, source_name: str) -> SourceStatus | None:
        """Get the status of a specific source."""
        return self._storage.get_status(source_name)

    def get_all_statuses(self) -> list[SourceStatus]:
        """Get the status of all tracked sources."""
        return self._storage.get_all_statuses()

    def _get_source_from_registry(self, source_name: str, source_type: str):
        """Retrieve the source configuration from the appropriate registry."""
        try:
            if source_type == "rss":
                return self._rss_registry.get_by_name(source_name)
            elif source_type == "github":
                return self._github_registry.get_by_name(source_name)
            elif source_type == "huggingface":
                return self._hf_registry.get_by_name(source_name)
        except KeyError:
            return None
        return None

    def _get_validator(self, source_type: str):
        """Get the appropriate validator for the source type."""
        if source_type == "rss":
            return self._rss_validator
        elif source_type == "github":
            return self._github_validator
        elif source_type == "huggingface":
            return self._hf_validator
        return None
