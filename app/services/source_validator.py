"""Source validation service for pre-flight checks.

This module provides validators for checking the accessibility and validity
of data sources (RSS, GitHub, HuggingFace) before they are added to the system.
"""

from typing import Any, Protocol

import httpx

from app.core.logger import get_logger
from app.models.source import GitHubRepository, HFSource, HFSourceType, RSSSource
from app.models.validation import ValidationResult

logger = get_logger(__name__)


class BaseValidator(Protocol):
    """Protocol for all validators in the system.

    This protocol defines a unified interface for validation operations,
    enabling consistent validation across different domains (Source Validation,
    LLM Output Validation, etc.).
    """

    def validate(self, target: Any) -> ValidationResult:
        """Validate the target and return a ValidationResult.

        Args:
            target: The object to validate.

        Returns:
            ValidationResult indicating success or failure with details.
        """
        ...


class RSSValidator:
    """Validator for RSS feed sources.

    Performs a HEAD request to check if the URL is accessible and returns
    valid RSS/Atom content.
    """

    def __init__(self, timeout: float = 10.0) -> None:
        """Initialize the validator with a timeout."""
        self._timeout = timeout

    def validate(self, source: RSSSource) -> ValidationResult:
        """Validate an RSS source by checking URL accessibility and content-type.

        Args:
            source: The RSS source to validate.

        Returns:
            ValidationResult indicating whether the source is valid.
        """
        logger.info("Validating RSS source: %s (%s)", source.name, source.url)

        try:
            response = httpx.head(
                source.url,
                timeout=self._timeout,
                follow_redirects=True,
                headers={"User-Agent": "AI-Radar/1.0"},
            )

            if response.status_code != 200:
                return ValidationResult.failure(
                    error_message=f"RSS feed returned status {response.status_code}",
                    details={"status_code": response.status_code, "url": source.url},
                )

            # Check content-type (should be XML or RSS/Atom)
            content_type = response.headers.get("content-type", "").lower()
            valid_types = [
                "application/xml",
                "text/xml",
                "application/rss+xml",
                "application/atom+xml",
            ]

            if not any(valid_type in content_type for valid_type in valid_types):
                return ValidationResult.failure(
                    error_message=f"Invalid content-type: {content_type}",
                    details={"content_type": content_type, "url": source.url},
                )

            logger.info("RSS source validation passed: %s", source.name)
            return ValidationResult.success(
                details={"url": source.url, "content_type": content_type}
            )

        except httpx.TimeoutException:
            logger.error("RSS validation timeout: %s", source.url)
            return ValidationResult.failure(
                error_message=f"Timeout while validating RSS feed (>{self._timeout}s)",
                details={"url": source.url, "timeout": self._timeout},
            )
        except httpx.RequestError as e:
            logger.error("RSS validation network error: %s - %s", source.url, e)
            return ValidationResult.failure(
                error_message=f"Network error: {str(e)}",
                details={"url": source.url, "error_type": type(e).__name__},
            )
        except Exception as e:
            logger.error("RSS validation unexpected error: %s - %s", source.url, e, exc_info=True)
            return ValidationResult.failure(
                error_message=f"Unexpected error: {str(e)}",
                details={"url": source.url, "error_type": type(e).__name__},
            )


class GitHubValidator:
    """Validator for GitHub repository sources.

    Performs a GET request to the GitHub API to check if the repository exists
    and is accessible.
    """

    def __init__(self, timeout: float = 10.0, token: str | None = None) -> None:
        """Initialize the validator with timeout and optional token."""
        self._timeout = timeout
        self._token = token

    def validate(self, source: GitHubRepository) -> ValidationResult:
        """Validate a GitHub repository by checking API accessibility.

        Args:
            source: The GitHub repository to validate.

        Returns:
            ValidationResult indicating whether the repository is accessible.
        """
        logger.info("Validating GitHub source: %s (%s/%s)", source.name, source.owner, source.repo)

        url = f"https://api.github.com/repos/{source.owner}/{source.repo}"
        headers = {"Accept": "application/vnd.github.v3+json"}

        if self._token:
            headers["Authorization"] = f"token {self._token}"

        try:
            response = httpx.get(url, timeout=self._timeout, headers=headers, follow_redirects=True)

            if response.status_code == 200:
                logger.info("GitHub source validation passed: %s", source.name)
                return ValidationResult.success(details={"url": url, "status_code": 200})
            elif response.status_code == 404:
                return ValidationResult.failure(
                    error_message="Repository not found or private (without access)",
                    details={"url": url, "status_code": 404},
                )
            elif response.status_code in [401, 403]:
                if response.status_code == 403:
                    rate_limit_remaining = response.headers.get("X-RateLimit-Remaining")
                    if rate_limit_remaining == "0":
                        return ValidationResult.failure(
                            error_message="GitHub API rate limit exceeded. "
                            "Set GITHUB_TOKEN in .env to increase limit.",
                            details={"url": url, "status_code": 403, "rate_limit_remaining": 0},
                        )
                    else:
                        return ValidationResult.failure(
                            error_message="GitHub API returned 403 Forbidden",
                            details={"url": url, "status_code": 403},
                        )
                return ValidationResult.failure(
                    error_message="Authentication failed or rate limit exceeded",
                    details={"url": url, "status_code": response.status_code},
                )
            else:
                return ValidationResult.failure(
                    error_message=f"GitHub API returned status {response.status_code}",
                    details={"url": url, "status_code": response.status_code},
                )

        except httpx.TimeoutException:
            logger.error("GitHub validation timeout: %s", url)
            return ValidationResult.failure(
                error_message=f"Timeout while validating GitHub repo (>{self._timeout}s)",
                details={"url": url, "timeout": self._timeout},
            )
        except httpx.RequestError as e:
            logger.error("GitHub validation network error: %s - %s", url, e)
            return ValidationResult.failure(
                error_message=f"Network error: {str(e)}",
                details={"url": url, "error_type": type(e).__name__},
            )
        except Exception as e:
            logger.error("GitHub validation unexpected error: %s - %s", url, e, exc_info=True)
            return ValidationResult.failure(
                error_message=f"Unexpected error: {str(e)}",
                details={"url": url, "error_type": type(e).__name__},
            )


class HuggingFaceValidator:
    """Validator for Hugging Face sources (datasets and models).

    Performs a GET request to the Hugging Face API to check if the resource exists.
    """

    def __init__(self, timeout: float = 10.0, token: str | None = None) -> None:
        """Initialize the validator with timeout and optional token."""
        self._timeout = timeout
        self._token = token

    def validate(self, source: HFSource) -> ValidationResult:
        """Validate a Hugging Face source by checking API accessibility.

        Args:
            source: The Hugging Face source to validate.

        Returns:
            ValidationResult indicating whether the resource is accessible.
        """
        logger.info(
            "Validating HuggingFace source: %s (%s - %s)",
            source.name,
            source.resource_id,
            source.source_type.value,
        )

        # Build URL based on source type
        if source.source_type == HFSourceType.DATASET:
            url = f"https://huggingface.co/api/datasets/{source.resource_id}"
        else:  # MODEL
            url = f"https://huggingface.co/api/models/{source.resource_id}"

        headers = {"Accept": "application/json"}

        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"

        try:
            response = httpx.get(url, timeout=self._timeout, headers=headers, follow_redirects=True)

            if response.status_code == 200:
                logger.info("HuggingFace source validation passed: %s", source.name)
                return ValidationResult.success(details={"url": url, "status_code": 200})
            elif response.status_code == 404:
                return ValidationResult.failure(
                    error_message="Resource not found or private (without access)",
                    details={"url": url, "status_code": 404},
                )
            elif response.status_code in [401, 403]:
                return ValidationResult.failure(
                    error_message="Authentication failed",
                    details={"url": url, "status_code": response.status_code},
                )
            else:
                return ValidationResult.failure(
                    error_message=f"Hugging Face API returned status {response.status_code}",
                    details={"url": url, "status_code": response.status_code},
                )

        except httpx.TimeoutException:
            logger.error("HuggingFace validation timeout: %s", url)
            return ValidationResult.failure(
                error_message=f"Timeout while validating HuggingFace resource (>{self._timeout}s)",
                details={"url": url, "timeout": self._timeout},
            )
        except httpx.RequestError as e:
            logger.error("HuggingFace validation network error: %s - %s", url, e)
            return ValidationResult.failure(
                error_message=f"Network error: {str(e)}",
                details={"url": url, "error_type": type(e).__name__},
            )
        except Exception as e:
            logger.error("HuggingFace validation unexpected error: %s - %s", url, e, exc_info=True)
            return ValidationResult.failure(
                error_message=f"Unexpected error: {str(e)}",
                details={"url": url, "error_type": type(e).__name__},
            )
