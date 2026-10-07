"""Tests for settings-driven discovery fetchers and pipeline wiring."""

from datetime import datetime
from unittest.mock import MagicMock, patch

from app.fetchers.discovery import (
    fetch_github_discovery,
    fetch_huggingface_discovery,
    merge_and_deduplicate_papers,
)
from app.models.article import RawArticle
from app.pipelines.acquisition import DefaultAcquisitionPipeline


def make_settings(**overrides):
    settings = MagicMock()
    settings.github_discovery_enabled = overrides.get("github_discovery_enabled", False)
    settings.github_discovery_topics = overrides.get("github_discovery_topics", ["llm", "rag"])
    settings.github_discovery_min_stars = overrides.get("github_discovery_min_stars", 20)
    settings.github_discovery_trending_since = overrides.get(
        "github_discovery_trending_since", "weekly"
    )
    settings.hf_discovery_enabled = overrides.get("hf_discovery_enabled", False)
    settings.hf_discovery_papers_limit = overrides.get("hf_discovery_papers_limit", 20)
    settings.hf_discovery_trending_limit = overrides.get("hf_discovery_trending_limit", 20)
    settings.hf_discovery_papers_date = overrides.get("hf_discovery_papers_date", None)
    settings.fetch_timeout = 5.0
    return settings


def make_raw(slug: str) -> RawArticle:
    return RawArticle(
        title=f"Discovered {slug}",
        url=f"https://example.com/discovery/{slug}",
        content="Discovered content body.",
        published_date=datetime(2026, 10, 7),
        source_name="discovery",
    )


class TestGitHubDiscovery:
    def test_disabled_returns_empty_without_fetching(self):
        settings = make_settings(github_discovery_enabled=False)

        with patch("app.fetchers.discovery.GitHubFetcher") as mock_fetcher_cls:
            result = fetch_github_discovery(settings)

        assert result == []
        mock_fetcher_cls.assert_not_called()

    def test_enabled_fetches_trending_and_topics(self):
        settings = make_settings(github_discovery_enabled=True)
        fetcher = MagicMock()
        fetcher.fetch_trending_repos.return_value = [{"repo": "a"}]
        fetcher.fetch_new_repos_by_topic.return_value = [{"repo": "b"}]
        parser = MagicMock()
        parser.parse_search_results.side_effect = [
            [make_raw("trending")],
            [make_raw("topic-llm")],
            [make_raw("topic-rag")],
        ]

        with (
            patch("app.fetchers.discovery.GitHubFetcher", return_value=fetcher),
            patch("app.fetchers.discovery.GitHubParser", return_value=parser),
        ):
            result = fetch_github_discovery(settings)

        assert len(result) == 3  # trending + 2 topics
        assert fetcher.fetch_new_repos_by_topic.call_count == 2

    def test_source_failure_is_best_effort(self):
        settings = make_settings(github_discovery_enabled=True)
        fetcher = MagicMock()
        fetcher.fetch_trending_repos.side_effect = Exception("GitHub down")
        fetcher.fetch_new_repos_by_topic.return_value = [{"repo": "b"}]
        parser = MagicMock()
        parser.parse_search_results.return_value = [make_raw("topic-llm")]

        with (
            patch("app.fetchers.discovery.GitHubFetcher", return_value=fetcher),
            patch("app.fetchers.discovery.GitHubParser", return_value=parser),
        ):
            result = fetch_github_discovery(settings)

        # Trending failed but topics still fetched
        assert len(result) == 2


class TestHuggingFaceDiscovery:
    def test_disabled_returns_empty_without_fetching(self):
        settings = make_settings(hf_discovery_enabled=False)

        with patch("app.fetchers.discovery.HuggingFaceFetcher") as mock_fetcher_cls:
            result = fetch_huggingface_discovery(settings)

        assert result == []
        mock_fetcher_cls.assert_not_called()

    def test_enabled_merges_papers_and_trending(self):
        settings = make_settings(hf_discovery_enabled=True, hf_discovery_papers_date="2026-10-07")
        fetcher = MagicMock()
        fetcher.fetch_daily_papers.return_value = [{"paper": {"id": "p1"}}]
        fetcher.fetch_papers_by_date.return_value = [{"id": "p1"}, {"id": "p2"}]
        fetcher.fetch_trending_models.return_value = [{"model": "m"}]
        fetcher.fetch_trending_datasets.return_value = [{"dataset": "d"}]
        parser = MagicMock()
        parser.parse_daily_papers.return_value = [make_raw("paper1"), make_raw("paper2")]
        parser.parse_trending_models.return_value = [make_raw("trending")]

        with (
            patch("app.fetchers.discovery.HuggingFaceFetcher", return_value=fetcher),
            patch("app.fetchers.discovery.HuggingFaceParser", return_value=parser),
        ):
            result = fetch_huggingface_discovery(settings)

        # 2 unique papers + 1 trending model + 1 trending dataset
        assert len(result) == 4
        fetcher.fetch_daily_papers.assert_called_once_with(date="2026-10-07")
        parser.parse_daily_papers.assert_called_once()


class TestMergeAndDeduplicatePapers:
    def test_daily_takes_priority_and_submitted_normalized(self):
        daily = [{"paper": {"id": "a"}}]
        submitted = [{"id": "a"}, {"id": "b"}]

        merged = merge_and_deduplicate_papers(daily, submitted)

        assert merged == [{"paper": {"id": "a"}}, {"paper": {"id": "b"}}]

    def test_empty_inputs(self):
        assert merge_and_deduplicate_papers([], []) == []


class TestPipelineDiscoveryWiring:
    """Discovery must flow into AcquisitionResult.articles when enabled."""

    @staticmethod
    def _make_pipeline(settings):
        return DefaultAcquisitionPipeline(
            rss_registry=MagicMock(get_all=lambda: []),
            github_registry=MagicMock(get_all=lambda: []),
            hf_registry=MagicMock(get_all=lambda: []),
            settings=settings,
        )

    @patch("app.pipelines.acquisition.save_acquisition_result")
    @patch("app.fetchers.discovery.fetch_huggingface_discovery", return_value=[])
    @patch("app.fetchers.discovery.fetch_github_discovery")
    def test_enabled_articles_reach_result(self, mock_gh, mock_hf, _mock_save, monkeypatch):
        monkeypatch.delenv("GITHUB_DISCOVERY_ENABLED", raising=False)
        mock_gh.return_value = [make_raw("gh1")]
        settings = make_settings(github_discovery_enabled=True, hf_discovery_enabled=True)
        pipeline = self._make_pipeline(settings)

        result = pipeline.run()

        mock_gh.assert_called_once_with(settings)
        mock_hf.assert_called_once_with(settings)
        assert [a.title for a in result.articles] == ["Discovered gh1"]
        assert result.total_articles == 1

    @patch("app.pipelines.acquisition.save_acquisition_result")
    @patch("app.fetchers.discovery.fetch_github_discovery")
    def test_disabled_settings_skip_discovery(self, mock_gh, _mock_save):
        settings = make_settings(github_discovery_enabled=False, hf_discovery_enabled=False)
        pipeline = self._make_pipeline(settings)

        result = pipeline.run()

        mock_gh.assert_not_called()
        assert result.articles == []

    @patch("app.pipelines.acquisition.save_acquisition_result")
    @patch("app.fetchers.discovery.fetch_github_discovery")
    def test_no_settings_disables_discovery(self, mock_gh, _mock_save):
        pipeline = self._make_pipeline(settings=None)

        result = pipeline.run()

        mock_gh.assert_not_called()
        assert result.articles == []
