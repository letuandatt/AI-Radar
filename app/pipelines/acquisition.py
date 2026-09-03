"""Default implementation of the Acquisition Pipeline.

This module provides the concrete implementation for orchestrating
the knowledge acquisition process from multiple sources (RSS, GitHub,
HuggingFace), handling errors gracefully, and aggregating results.
"""

import time
from datetime import datetime

from app.core.logger import get_logger
from app.fetchers.github import GitHubFetcher
from app.fetchers.github_parser import GitHubParser
from app.fetchers.huggingface import HuggingFaceFetcher
from app.fetchers.huggingface_parser import HuggingFaceParser
from app.fetchers.registry import (
    ConfigBasedGitHubRegistry,
    ConfigBasedHFRegistry,
    ConfigBasedSourceRegistry,
)
from app.fetchers.rss import RSSFetcher
from app.fetchers.rss_parser import RSSParser
from app.models.result import AcquisitionResult, SourceError
from app.storage.history import save_acquisition_result

logger = get_logger(__name__)


class DefaultAcquisitionPipeline:
    """Default implementation of the Acquisition Pipeline.

    This pipeline orchestrates the acquisition process by:
    1. Loading all registered sources from RSS, GitHub, and HuggingFace registries.
    2. For each source, fetching raw data and parsing it into RawArticles.
    3. Aggregating results (success/failure counts, article counts, errors).
    4. Returning an AcquisitionResult with execution metrics.

    The pipeline is fault-tolerant: if a source fails, it logs the error
    and continues with the next source. It is also scheduler-independent:
    it does not contain any logic related to cron jobs or scheduling.
    """

    def __init__(
        self,
        rss_registry: ConfigBasedSourceRegistry,
        github_registry: ConfigBasedGitHubRegistry,
        hf_registry: ConfigBasedHFRegistry,
    ) -> None:
        """Initialize the pipeline with the required registries.

        Args:
            rss_registry: Registry containing RSS sources.
            github_registry: Registry containing GitHub sources.
            hf_registry: Registry containing HuggingFace sources.
        """
        self._rss_registry = rss_registry
        self._github_registry = github_registry
        self._hf_registry = hf_registry

        # Initialize fetchers and parsers once for efficiency
        self._rss_fetcher = RSSFetcher()
        self._rss_parser = RSSParser()
        self._github_fetcher = GitHubFetcher()
        self._github_parser = GitHubParser()
        self._hf_fetcher = HuggingFaceFetcher()
        self._hf_parser = HuggingFaceParser()

        logger.info("DefaultAcquisitionPipeline initialized")

    def run(self) -> AcquisitionResult:
        """Execute the acquisition process from all registered sources.

        Returns:
            AcquisitionResult: The aggregated result of the acquisition run,
            including success/failure counts and detailed error logs.
        """
        start_time = time.time()
        errors: list[SourceError] = []
        total_articles = 0
        successful_sources = 0
        failed_sources = 0

        logger.info("Starting acquisition pipeline execution")

        # Process RSS sources
        rss_sources = self._rss_registry.get_all()
        logger.info("Processing %d RSS sources", len(rss_sources))
        for source in rss_sources:
            try:
                raw_data = self._rss_fetcher.fetch_raw(source)
                articles = self._rss_parser.parse(raw_data, source)
                total_articles += len(articles)
                successful_sources += 1
                logger.info(
                    "Successfully processed RSS source: %s (%d articles)",
                    source.name,
                    len(articles),
                )
            except Exception as e:
                failed_sources += 1
                error = SourceError(
                    source_name=source.name,
                    source_type="rss",
                    error_type=type(e).__name__,
                    error_message=str(e),
                )
                errors.append(error)
                logger.error("Failed to process RSS source %s: %s", source.name, e)

        # Process GitHub sources
        github_sources = self._github_registry.get_all()
        logger.info("Processing %d GitHub sources", len(github_sources))
        for repo in github_sources:
            try:
                # Fetch commits and issues separately
                commits_data = self._github_fetcher.fetch_commits(repo)
                commits = self._github_parser.parse_commits(commits_data, repo)

                issues_data = self._github_fetcher.fetch_issues(repo)
                issues = self._github_parser.parse_issues(issues_data, repo)

                total_articles += len(commits) + len(issues)
                successful_sources += 1
                logger.info(
                    "Successfully processed GitHub source: %s (%d commits, %d issues)",
                    repo.name,
                    len(commits),
                    len(issues),
                )
            except Exception as e:
                failed_sources += 1
                error = SourceError(
                    source_name=repo.name,
                    source_type="github",
                    error_type=type(e).__name__,
                    error_message=str(e),
                )
                errors.append(error)
                logger.error("Failed to process GitHub source %s: %s", repo.name, e)

        # Process HuggingFace sources
        hf_sources = self._hf_registry.get_all()
        logger.info("Processing %d HuggingFace sources", len(hf_sources))
        for hf_source in hf_sources:  # Đổi 'source' thành 'hf_source'
            try:
                data = self._hf_fetcher.fetch_json(hf_source)
                articles = self._hf_parser.parse(data, hf_source)
                total_articles += len(articles)
                successful_sources += 1
                logger.info(
                    "Successfully processed HuggingFace source: %s (%d articles)",
                    hf_source.name,
                    len(articles),
                )
            except Exception as e:
                failed_sources += 1
                error = SourceError(
                    source_name=hf_source.name,
                    source_type="huggingface",
                    error_type=type(e).__name__,
                    error_message=str(e),
                )
                errors.append(error)
                logger.error("Failed to process HuggingFace source %s: %s", hf_source.name, e)

        execution_time = time.time() - start_time

        result = AcquisitionResult(
            timestamp=datetime.now(),
            total_sources=successful_sources + failed_sources,
            successful_sources=successful_sources,
            failed_sources=failed_sources,
            total_articles=total_articles,
            execution_time=execution_time,
            errors=errors,
        )

        logger.info(
            "Acquisition pipeline completed: %d sources (%d success, %d failed), "
            "%d articles in %.2f seconds",
            result.total_sources,
            result.successful_sources,
            result.failed_sources,
            result.total_articles,
            result.execution_time,
        )

        try:
            save_acquisition_result(result)
        except Exception as e:
            logger.error("Failed to save acquisition result: %s", e)

        return result
