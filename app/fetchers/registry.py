"""Source Registry implementation and access path.

This module provides the concrete implementation of the SourceRegistry
that loads data source configurations from the application settings.
"""

from app.config.settings import Settings
from app.core.logger import get_logger
from app.fetchers.exceptions import DuplicateSourceError
from app.models.source import GitHubRepository, RSSSource

logger = get_logger(__name__)


# ==========================================
# RSS Source Registry
# ==========================================


class ConfigBasedSourceRegistry:
    """A source registry that loads configurations from application settings.

    This registry operates in-memory for high-performance access during runtime.
    It is initialized once during application startup and remains read-only
    throughout the application's lifecycle.
    """

    def __init__(self, settings: Settings) -> None:
        """Initialize the registry and load sources from settings."""
        self._sources: dict[str, RSSSource] = {}
        self._load_from_config(settings)

    def _load_from_config(self, settings: Settings) -> None:
        """Parse and load RSS sources from the provided settings."""
        for source_config in settings.rss_sources:
            name = source_config.get("name")
            url = source_config.get("url")

            if not name or not url:
                logger.warning(
                    "Skipping invalid RSS source config (missing 'name' or 'url'): %s",
                    source_config,
                )
                continue

            source = RSSSource(name=name, url=url)
            try:
                self.register(source)
            except DuplicateSourceError as e:
                logger.warning("Skipping duplicate source in config: %s", e)

    def register(self, source: RSSSource) -> None:
        """Register a new data source."""
        if source.name in self._sources:
            raise DuplicateSourceError(f"Source with name '{source.name}' is already registered.")
        self._sources[source.name] = source
        logger.debug("Registered source: %s", source.name)

    def get_all(self) -> list[RSSSource]:
        """Retrieve all registered data sources."""
        return list(self._sources.values())

    def get_by_name(self, name: str) -> RSSSource:
        """Retrieve a specific data source by its unique name."""
        if name not in self._sources:
            raise KeyError(f"Source '{name}' not found in registry.")
        return self._sources[name]


# --- Singleton Access Path ---

_registry: ConfigBasedSourceRegistry | None = None


def initialize_source_registry(settings: Settings) -> None:
    """Initialize the global source registry from settings."""
    global _registry

    if _registry is not None:
        logger.warning("Source registry is already initialized. Skipping.")
        return

    _registry = ConfigBasedSourceRegistry(settings)
    logger.info(
        "Source registry initialized successfully with %d sources.", len(_registry.get_all())
    )


def get_source_registry() -> ConfigBasedSourceRegistry:
    """Return the global source registry instance.

    Raises:
        RuntimeError: If the registry has not been initialized yet.
    """
    if _registry is None:
        raise RuntimeError(
            "Source registry is not initialized. "
            "Ensure initialize_source_registry() is called during application startup."
        )
    return _registry


# ==========================================
# GitHub Repository Registry
# ==========================================


class ConfigBasedGitHubRegistry:
    """A registry that loads GitHub repository configurations from settings.

    Operates in-memory for high-performance access. Initialized once
    during startup and remains read-only at runtime.
    """

    def __init__(self, settings: Settings) -> None:
        """Initialize the registry and load repositories from settings."""
        self._repositories: dict[str, GitHubRepository] = {}
        self._load_from_config(settings)

    def _load_from_config(self, settings: Settings) -> None:
        """Parse and load GitHub repositories from the provided settings."""
        for repo_config in settings.github_repositories:
            name = repo_config.get("name")
            owner = repo_config.get("owner")
            repo = repo_config.get("repo")

            if not name or not owner or not repo:
                logger.warning(
                    "Skipping invalid GitHub repo config (missing 'name', 'owner', or 'repo'): %s",
                    repo_config,
                )
                continue

            repository = GitHubRepository(name=name, owner=owner, repo=repo)
            try:
                self.register(repository)
            except DuplicateSourceError as e:
                logger.warning("Skipping duplicate repository in config: %s", e)

    def register(self, repository: GitHubRepository) -> None:
        """Register a new GitHub repository."""
        if repository.name in self._repositories:
            raise DuplicateSourceError(
                f"Repository with name '{repository.name}' is already registered."
            )
        self._repositories[repository.name] = repository
        logger.debug("Registered GitHub repository: %s/%s", repository.owner, repository.repo)

    def get_all(self) -> list[GitHubRepository]:
        """Retrieve all registered GitHub repositories."""
        return list(self._repositories.values())

    def get_by_name(self, name: str) -> GitHubRepository:
        """Retrieve a specific GitHub repository by its unique name."""
        if name not in self._repositories:
            raise KeyError(f"Repository '{name}' not found in registry.")
        return self._repositories[name]


_github_registry: ConfigBasedGitHubRegistry | None = None


def initialize_github_registry(settings: Settings) -> None:
    """Initialize the global GitHub registry from settings."""
    global _github_registry

    if _github_registry is not None:
        logger.warning("GitHub registry is already initialized. Skipping.")
        return

    _github_registry = ConfigBasedGitHubRegistry(settings)
    logger.info(
        "GitHub registry initialized successfully with %d repositories.",
        len(_github_registry.get_all()),
    )


def get_github_registry() -> ConfigBasedGitHubRegistry:
    """Return the global GitHub registry instance.

    Raises:
        RuntimeError: If the registry has not been initialized yet.
    """
    if _github_registry is None:
        raise RuntimeError(
            "GitHub registry is not initialized. "
            "Ensure initialize_github_registry() is called during application startup."
        )
    return _github_registry
