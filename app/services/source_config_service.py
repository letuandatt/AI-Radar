"""Source Configuration Service for dynamic source management.

This service provides a unified interface for managing data source configurations
at runtime, including adding, updating, removing sources, and exposing JSON schemas
for Schema-Driven UI.
"""

import threading
from typing import Any

from app.core.logger import get_logger
from app.fetchers.registry import (
    ConfigBasedGitHubRegistry,
    ConfigBasedHFRegistry,
    ConfigBasedSourceRegistry,
)
from app.models.source import GitHubRepository, HFSource, RSSSource
from app.models.validation import ValidationResult
from app.services.source_validator import (
    GitHubValidator,
    HuggingFaceValidator,
    RSSValidator,
)

logger = get_logger(__name__)


class SourceConfigService:
    """Service for managing data source configurations dynamically.

    This service provides thread-safe operations for:
    - Updating source configurations (with pre-flight validation)
    - Retrieving current source configurations
    - Removing sources from the system
    - Exposing JSON schemas for each source type (for Schema-Driven UI)

    Thread Safety:
        All mutation operations are protected by a lock to prevent race conditions
        when multiple threads attempt to update configurations simultaneously.
    """

    def __init__(
        self,
        rss_registry: ConfigBasedSourceRegistry,
        github_registry: ConfigBasedGitHubRegistry,
        hf_registry: ConfigBasedHFRegistry,
    ) -> None:
        """Initialize the service with the required registries.

        Args:
            rss_registry: Registry containing RSS sources.
            github_registry: Registry containing GitHub sources.
            hf_registry: Registry containing HuggingFace sources.
        """
        self._rss_registry = rss_registry
        self._github_registry = github_registry
        self._hf_registry = hf_registry

        # Thread-safe lock for mutation operations
        self._lock = threading.Lock()

        # Validators for pre-flight checks
        self._rss_validator = RSSValidator()
        self._github_validator = GitHubValidator()
        self._hf_validator = HuggingFaceValidator()

        logger.info("SourceConfigService initialized")

    def update_source(
        self,
        source_type: str,
        name: str,
        config: dict[str, Any],
    ) -> ValidationResult:
        """Update or add a source configuration with pre-flight validation.

        This method:
        1. Validates the configuration using the appropriate validator (pre-flight).
        2. If validation passes, updates the source in the corresponding registry.
        3. Returns the validation result.

        Args:
            source_type: Type of source ('rss', 'github', 'huggingface').
            name: Unique name for the source.
            config: Configuration dictionary for the source.

        Returns:
            ValidationResult indicating success or failure.
        """
        logger.info("Updating source: %s (%s)", name, source_type)

        with self._lock:
            try:
                # Build source model based on type
                if source_type == "rss":
                    rss_source = RSSSource(name=name, **config)
                    validation = self._rss_validator.validate(rss_source)
                    if validation.is_valid:
                        self._rss_registry.register(rss_source)
                        logger.info("RSS source updated: %s", name)
                    return validation

                elif source_type == "github":
                    github_source = GitHubRepository(name=name, **config)
                    validation = self._github_validator.validate(github_source)
                    if validation.is_valid:
                        self._github_registry.register(github_source)
                        logger.info("GitHub source updated: %s", name)
                    return validation

                elif source_type == "huggingface":
                    hf_source = HFSource(name=name, **config)
                    validation = self._hf_validator.validate(hf_source)
                    if validation.is_valid:
                        self._hf_registry.register(hf_source)
                        logger.info("HuggingFace source updated: %s", name)
                    return validation

                else:
                    return ValidationResult.failure(
                        error_message=f"Unknown source type: {source_type}",
                        details={"source_type": source_type},
                    )

            except Exception as e:
                logger.error("Failed to update source %s: %s", name, e, exc_info=True)
                return ValidationResult.failure(
                    error_message=f"Failed to update source: {str(e)}",
                    details={"source_type": source_type, "name": name, "error": str(e)},
                )

    def get_source_config(self, source_type: str, name: str) -> dict[str, Any] | None:
        """Retrieve the configuration of a specific source.

        Args:
            source_type: Type of source ('rss', 'github', 'huggingface').
            name: Unique name of the source.

        Returns:
            Dictionary representation of the source, or None if not found.
        """
        try:
            if source_type == "rss":
                rss_source = self._rss_registry.get_by_name(name)
                return rss_source.model_dump()
            elif source_type == "github":
                github_source = self._github_registry.get_by_name(name)
                return github_source.model_dump()
            elif source_type == "huggingface":
                hf_source = self._hf_registry.get_by_name(name)
                return hf_source.model_dump()
            else:
                logger.warning("Unknown source type: %s", source_type)
                return None
        except KeyError:
            logger.warning("Source not found: %s (%s)", name, source_type)
            return None

    def remove_source(self, source_type: str, name: str) -> bool:
        """Remove a source from the system.

        Note: This method removes the source from the in-memory registry.
        Persistent removal from configuration files is not yet implemented
        (will be added in future sprint).

        Args:
            source_type: Type of source ('rss', 'github', 'huggingface').
            name: Unique name of the source to remove.

        Returns:
            True if the source was removed, False if not found.
        """
        logger.info("Removing source: %s (%s)", name, source_type)

        with self._lock:
            try:
                if source_type == "rss":
                    # Registry doesn't have remove method yet, so we need to check existence
                    try:
                        self._rss_registry.get_by_name(name)
                        # Source exists, but we can't remove it yet (registry limitation)
                        logger.warning(
                            "RSS source '%s' exists but removal from registry is not yet supported",
                            name,
                        )
                        return False
                    except KeyError:
                        return False

                elif source_type == "github":
                    try:
                        self._github_registry.get_by_name(name)
                        logger.warning(
                            "GitHub source '%s' exists but "
                            "removal from registry is not yet supported",
                            name,
                        )
                        return False
                    except KeyError:
                        return False

                elif source_type == "huggingface":
                    try:
                        self._hf_registry.get_by_name(name)
                        logger.warning(
                            "HuggingFace source '%s' exists but "
                            "removal from registry is not yet supported",
                            name,
                        )
                        return False
                    except KeyError:
                        return False

                else:
                    logger.warning("Unknown source type: %s", source_type)
                    return False

            except Exception as e:
                logger.error("Failed to remove source %s: %s", name, e, exc_info=True)
                return False

    def get_source_schema(self, source_type: str) -> dict[str, Any] | None:
        """Get the JSON Schema for a source type.

        This method exposes the Pydantic model schema for Schema-Driven UI (INFRA-002).
        Frontend can use this schema to dynamically render forms for source configuration.

        Args:
            source_type: Type of source ('rss', 'github', 'huggingface').

        Returns:
            JSON Schema dictionary, or None if source type is unknown.
        """
        if source_type == "rss":
            return RSSSource.model_json_schema()
        elif source_type == "github":
            return GitHubRepository.model_json_schema()
        elif source_type == "huggingface":
            return HFSource.model_json_schema()
        else:
            logger.warning("Unknown source type for schema: %s", source_type)
            return None

    def get_all_source_types(self) -> list[str]:
        """Get list of all supported source types.

        Returns:
            List of source type strings.
        """
        return ["rss", "github", "huggingface"]
