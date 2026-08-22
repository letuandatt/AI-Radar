"""Base contracts and interfaces for the Pipelines layer.

This module defines the foundational protocols that all pipeline components
must adhere to, ensuring loose coupling and high testability.
"""

from typing import Protocol

from app.models.result import AcquisitionResult


class AcquisitionPipeline(Protocol):
    """Contract for orchestrating the knowledge acquisition process.

    Implementations of this protocol are responsible for fetching data
    from all registered sources, parsing it into RawArticles, and
    aggregating the results.

    Note: This protocol is strictly scheduler-independent (ARCH-004).
    It does not contain any logic or parameters related to cron jobs,
    intervals, or scheduling.
    """

    def run(self) -> AcquisitionResult:
        """Execute the acquisition process from all registered sources.

        Returns:
            AcquisitionResult: The aggregated result of the acquisition run,
            including success/failure counts and detailed error logs.
        """
        ...
