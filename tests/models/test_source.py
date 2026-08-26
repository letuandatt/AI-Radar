"""Tests for Source data models."""

import pytest
from pydantic import ValidationError

from app.models.source import GitHubRepository, HFSource, HFSourceType, RSSSource


def test_rss_source_creation():
    """Verify that an RSSSource can be created with required fields."""
    source = RSSSource(name="tech_crunch", url="https://techcrunch.com/feed/")

    assert source.name == "tech_crunch"
    assert source.url == "https://techcrunch.com/feed/"
    assert source.is_active is True  # Default value


def test_rss_source_inactive():
    """Verify that an RSSSource can be explicitly set to inactive."""
    source = RSSSource(name="old_blog", url="http://old.com/rss", is_active=False)

    assert source.is_active is False


def test_rss_source_is_immutable():
    """Verify that RSSSource is frozen (immutable) to prevent accidental modification."""
    source = RSSSource(name="test", url="http://test.com")

    with pytest.raises(ValidationError):
        source.name = "new_name"


def test_github_repository_creation():
    """Verify that a GitHubRepository can be created with required fields."""
    repo = GitHubRepository(name="fastapi", owner="tiangolo", repo="fastapi")

    assert repo.name == "fastapi"
    assert repo.owner == "tiangolo"
    assert repo.repo == "fastapi"
    assert repo.is_active is True  # Default value


def test_github_repository_inactive():
    """Verify that a GitHubRepository can be explicitly set to inactive."""
    repo = GitHubRepository(name="old_repo", owner="user", repo="repo", is_active=False)

    assert repo.is_active is False


def test_github_repository_is_immutable():
    """Verify that GitHubRepository is frozen (immutable)."""
    repo = GitHubRepository(name="test", owner="user", repo="repo")

    with pytest.raises(ValidationError):
        repo.name = "new_name"


def test_hf_source_type_enum():
    """Verify that HFSourceType enum has the correct values."""
    assert HFSourceType.DATASET.value == "dataset"
    assert HFSourceType.MODEL.value == "model"


def test_hf_source_creation():
    """Verify that an HFSource can be created with required fields."""
    source = HFSource(
        name="bert_base",
        resource_id="google-bert/bert-base-uncased",
        source_type=HFSourceType.MODEL,
    )

    assert source.name == "bert_base"
    assert source.resource_id == "google-bert/bert-base-uncased"
    assert source.source_type == HFSourceType.MODEL
    assert source.is_active is True  # Default value


def test_hf_source_is_immutable():
    """Verify that HFSource is frozen (immutable)."""
    source = HFSource(name="test", resource_id="test/test", source_type=HFSourceType.DATASET)

    with pytest.raises(ValidationError):
        source.name = "new_name"
