"""Base contracts and interfaces for the Fetchers layer.

This module defines the foundational protocols that all fetcher components
must adhere to, ensuring loose coupling and high testability.
"""

from typing import Protocol

from app.models.article import RawArticle
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


class Fetcher(Protocol):
    """Contract for retrieving raw data from a source.

    Implementations of this protocol are responsible for establishing
    network connections, handling timeouts, and returning the raw
    string content (e.g., XML, HTML, JSON) from the target source.
    """

    def fetch_raw(self, source: RSSSource) -> str:
        """Fetch raw content from the specified source.

        Args:
            source: The data source to fetch from.

        Returns:
            The raw string content of the feed/data.

        Raises:
            NetworkError: If the connection cannot be established.
            FetchTimeoutError: If the request exceeds the time limit.
            HTTPStatusError: If the server returns a 4xx or 5xx status code.
        """
        ...


class Parser(Protocol):
    """Contract for parsing raw data into structured models.

    Implementations of this protocol are responsible for transforming
    raw string content (e.g., XML, HTML) into a list of domain models
    (e.g., RawArticle).
    """

    def parse(self, raw_data: str, source: RSSSource) -> list[RawArticle]:
        """Parse raw data into a list of RawArticle models.

        Args:
            raw_data: The raw string content to parse.
            source: The source from which the data was fetched.

        Returns:
            A list of parsed RawArticle instances.

        Raises:
            ParsingError: If the raw data is fundamentally malformed
                          and cannot be parsed at all.
        """
        ...
