"""Tests for GitHub Repository Registry implementation."""

from unittest.mock import MagicMock

import pytest

import app.fetchers.registry as registry_module
from app.config.settings import Settings
from app.fetchers.exceptions import DuplicateSourceError
from app.fetchers.registry import (
    ConfigBasedGitHubRegistry,
    get_github_registry,
    initialize_github_registry,
)
from app.models.source import GitHubRepository

# --- Fixtures ---


@pytest.fixture(autouse=True)
def reset_github_singleton_state():
    """Reset the global GitHub registry state before and after each test."""
    registry_module._github_registry = None
    yield
    registry_module._github_registry = None


@pytest.fixture
def mock_settings():
    """Provide a mock Settings object."""
    settings = MagicMock(spec=Settings)
    settings.github_repositories = []
    return settings


# --- Tests for ConfigBasedGitHubRegistry ---


def test_register_repository_success(mock_settings):
    """Verify that a repository can be registered and retrieved."""
    registry = ConfigBasedGitHubRegistry(mock_settings)
    repo = GitHubRepository(name="fastapi", owner="tiangolo", repo="fastapi")

    registry.register(repo)

    result = registry.get_by_name("fastapi")
    assert result is repo


def test_register_duplicate_repository_raises_error(mock_settings):
    """Verify that registering a duplicate repository raises DuplicateSourceError."""
    registry = ConfigBasedGitHubRegistry(mock_settings)
    repo1 = GitHubRepository(name="duplicate", owner="user1", repo="repo1")
    repo2 = GitHubRepository(name="duplicate", owner="user2", repo="repo2")

    registry.register(repo1)

    with pytest.raises(DuplicateSourceError, match="Repository with name 'duplicate'"):
        registry.register(repo2)


def test_get_all_returns_all_repositories(mock_settings):
    """Verify that get_all returns all registered repositories."""
    registry = ConfigBasedGitHubRegistry(mock_settings)
    repo1 = GitHubRepository(name="repo1", owner="user1", repo="repo1")
    repo2 = GitHubRepository(name="repo2", owner="user2", repo="repo2")

    registry.register(repo1)
    registry.register(repo2)

    result = registry.get_all()
    assert len(result) == 2
    assert repo1 in result
    assert repo2 in result


def test_get_by_name_not_found_raises_error(mock_settings):
    """Verify that getting a non-existent repository raises KeyError."""
    registry = ConfigBasedGitHubRegistry(mock_settings)

    with pytest.raises(KeyError, match="Repository 'missing' not found"):
        registry.get_by_name("missing")


# --- Tests for Configuration Loading ---


def test_registry_loads_from_settings():
    """Verify that the registry automatically loads repositories from settings."""
    settings = MagicMock(spec=Settings)
    settings.github_repositories = [
        {"name": "fastapi", "owner": "tiangolo", "repo": "fastapi"},
        {"name": "pydantic", "owner": "pydantic", "repo": "pydantic"},
    ]

    registry = ConfigBasedGitHubRegistry(settings)

    assert len(registry.get_all()) == 2
    assert registry.get_by_name("fastapi").owner == "tiangolo"
    assert registry.get_by_name("pydantic").repo == "pydantic"


def test_registry_skips_invalid_config(caplog):
    """Verify that invalid config items (missing name/owner/repo) are skipped."""
    settings = MagicMock(spec=Settings)
    settings.github_repositories = [
        {"name": "valid", "owner": "user", "repo": "repo"},
        {"name": "no_repo", "owner": "user"},  # Missing repo
        {"owner": "user", "repo": "repo"},  # Missing name
    ]

    import logging

    with caplog.at_level(logging.WARNING):
        registry = ConfigBasedGitHubRegistry(settings)

    assert len(registry.get_all()) == 1
    assert registry.get_by_name("valid").repo == "repo"
    assert "Skipping invalid GitHub repo config" in caplog.text


def test_registry_skips_duplicate_in_config(caplog):
    """Verify that duplicate repositories in config are skipped."""
    settings = MagicMock(spec=Settings)
    settings.github_repositories = [
        {"name": "duplicate", "owner": "user1", "repo": "repo1"},
        {"name": "duplicate", "owner": "user2", "repo": "repo2"},
    ]

    import logging

    with caplog.at_level(logging.WARNING):
        registry = ConfigBasedGitHubRegistry(settings)

    assert len(registry.get_all()) == 1
    assert registry.get_by_name("duplicate").owner == "user1"
    assert "Skipping duplicate repository in config" in caplog.text


# --- Tests for Singleton Access Path ---


def test_initialize_github_registry_creates_singleton():
    """Verify that initialize_github_registry creates the global instance."""
    settings = MagicMock(spec=Settings)
    settings.github_repositories = [{"name": "test", "owner": "user", "repo": "repo"}]

    initialize_github_registry(settings)

    result = get_github_registry()
    assert isinstance(result, ConfigBasedGitHubRegistry)
    assert len(result.get_all()) == 1


def test_initialize_github_registry_is_idempotent():
    """Verify that calling initialize twice does not overwrite the existing instance."""
    settings1 = MagicMock(spec=Settings)
    settings1.github_repositories = [{"name": "first", "owner": "user1", "repo": "repo1"}]

    settings2 = MagicMock(spec=Settings)
    settings2.github_repositories = [{"name": "second", "owner": "user2", "repo": "repo2"}]

    initialize_github_registry(settings1)
    first_registry = get_github_registry()

    initialize_github_registry(settings2)  # Should be ignored
    second_registry = get_github_registry()

    assert first_registry is second_registry
    assert len(second_registry.get_all()) == 1  # Still only has 'first'


def test_get_github_registry_raises_if_not_initialized():
    """Verify that get_github_registry raises RuntimeError if not initialized."""
    # _github_registry is None due to the autouse fixture
    with pytest.raises(RuntimeError, match="GitHub registry is not initialized"):
        get_github_registry()
