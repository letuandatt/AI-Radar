"""Base contracts and interfaces for the Fetchers layer.

This module defines the foundational protocols that all fetcher components
must adhere to, ensuring loose coupling and high testability.
"""

from typing import Protocol

from app.models.source import RSSSource


class SourceRegistry(Protocol):
    """Contract for managing data source registrations.

    Implementations of this protocol are responsible for storing,
    retrieving, and validating data source configurations.
    """

    def register(self, source: RSSSource) -> None:
        """Register a new data source.

        Args:
            source: The RSSSource instance to register.

        Raises:
            DuplicateSourceError: If a source with the same name already exists.
        """
        ...

    def get_all(self) -> list[RSSSource]:
        """Retrieve all registered data sources."""
        ...

    def get_by_name(self, name: str) -> RSSSource:
        """Retrieve a specific data source by its unique name.

        Args:
            name: The unique name of the source.

        Raises:
            KeyError: If no source with the given name is found.
        """
        ...
