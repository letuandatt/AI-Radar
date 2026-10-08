"""Source discovery fetchers (official, settings-driven).

Discovers NEW sources beyond the statically configured ones: GitHub trending
and topic repos, HuggingFace daily papers and trending models/datasets.

All fetches are best-effort — individual source failures are logged, never
raised, because discovery must never break the main acquisition run.
Enabled via Settings: ``github_discovery_enabled`` / ``hf_discovery_enabled``
(both default False).
"""

from datetime import datetime, timezone

from app.config.settings import Settings
from app.core.logger import get_logger
from app.fetchers.github import GitHubFetcher
from app.fetchers.github_parser import GitHubParser
from app.fetchers.huggingface import HuggingFaceFetcher
from app.fetchers.huggingface_parser import HuggingFaceParser
from app.models.article import RawArticle

logger = get_logger(__name__)


def fetch_github_discovery(settings: Settings) -> list[RawArticle]:
    """Fetch discovery articles from GitHub (trending + new repos by topic).

    Args:
        settings: Application settings (github_discovery_* fields).

    Returns:
        Discovered RawArticles, [] when disabled. Never raises.
    """
    if not settings.github_discovery_enabled:
        logger.info("GitHub discovery is disabled, skipping")
        return []

    fetcher = GitHubFetcher(timeout=settings.fetch_timeout)
    parser = GitHubParser()
    all_articles: list[RawArticle] = []

    # 1. Trending repos
    try:
        trending = fetcher.fetch_trending_repos(
            language="python",
            since=settings.github_discovery_trending_since,
        )
        trending_articles = parser.parse_search_results(trending, "github-trending")
        logger.info("GitHub trending: %d repos", len(trending_articles))
        all_articles.extend(trending_articles)
    except Exception as e:
        logger.error("GitHub trending FAILED: %s", e)

    # 2. New repos by topic
    for topic in settings.github_discovery_topics:
        try:
            repos = fetcher.fetch_new_repos_by_topic(
                topic=topic,
                min_stars=settings.github_discovery_min_stars,
                per_page=10,
            )
            topic_articles = parser.parse_search_results(repos, f"github-topic-{topic}")
            logger.info("GitHub topic [%s]: %d repos", topic, len(topic_articles))
            all_articles.extend(topic_articles)
        except Exception as e:
            logger.error("GitHub topic [%s] FAILED: %s", topic, e)

    return all_articles


def fetch_huggingface_discovery(settings: Settings) -> list[RawArticle]:
    """Fetch discovery articles from HuggingFace (papers + trending).

    Papers strategy: fetch BOTH daily_papers (curated) and papers_by_date
    (submitted on date), then merge and deduplicate by paper ID.

    Args:
        settings: Application settings (hf_discovery_* fields).

    Returns:
        Discovered RawArticles, [] when disabled. Never raises.
    """
    if not settings.hf_discovery_enabled:
        logger.info("HuggingFace discovery is disabled, skipping")
        return []

    fetcher = HuggingFaceFetcher(timeout=settings.fetch_timeout)
    parser = HuggingFaceParser()
    all_articles: list[RawArticle] = []

    # Determine target date
    if settings.hf_discovery_papers_date:
        target_date = settings.hf_discovery_papers_date
    else:
        target_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # 1. Papers: both endpoints, merged
    daily_papers: list[dict] = []
    try:
        daily_papers = fetcher.fetch_daily_papers(date=target_date)
        logger.info("HF daily_papers: %d papers", len(daily_papers))
    except Exception as e:
        logger.error("HF daily_papers FAILED: %s", e)

    submitted_papers: list[dict] = []
    try:
        submitted_papers = fetcher.fetch_papers_by_date(target_date)
        logger.info("HF papers_by_date: %d papers", len(submitted_papers))
    except Exception as e:
        logger.error("HF papers_by_date FAILED: %s", e)

    merged_papers = merge_and_deduplicate_papers(daily_papers, submitted_papers)
    logger.info(
        "HF papers merged: %d unique papers (from %d daily + %d submitted)",
        len(merged_papers),
        len(daily_papers),
        len(submitted_papers),
    )
    merged_papers = merged_papers[: settings.hf_discovery_papers_limit]
    paper_articles = parser.parse_daily_papers(merged_papers, "hf-papers")
    all_articles.extend(paper_articles)

    # 2. Trending models
    try:
        models = fetcher.fetch_trending_models(limit=settings.hf_discovery_trending_limit)
        model_articles = parser.parse_trending_models(models, "hf-trending-models")
        logger.info("HF trending models: %d models", len(model_articles))
        all_articles.extend(model_articles)
    except Exception as e:
        logger.error("HF trending models FAILED: %s", e)

    # 3. Trending datasets
    try:
        datasets = fetcher.fetch_trending_datasets(limit=settings.hf_discovery_trending_limit)
        dataset_articles = parser.parse_trending_models(datasets, "hf-trending-datasets")
        logger.info("HF trending datasets: %d datasets", len(dataset_articles))
        all_articles.extend(dataset_articles)
    except Exception as e:
        logger.error("HF trending datasets FAILED: %s", e)

    return all_articles


def merge_and_deduplicate_papers(
    daily_papers: list[dict], submitted_papers: list[dict]
) -> list[dict]:
    """Merge papers from daily_papers and papers_by_date, deduplicate by ID.

    The two endpoints have slightly different structures:
    - daily_papers: {"paper": {"id": "...", ...}, "paper_upvotes": N}
    - papers_by_date: {"id": "...", "title": "...", ...}

    Args:
        daily_papers: Papers from /api/daily_papers endpoint (higher priority).
        submitted_papers: Papers from /api/papers?date= endpoint.

    Returns:
        Merged list of unique papers; submitted ones normalized to the
        daily_papers shape.
    """
    seen_ids: set[str] = set()
    merged: list[dict] = []

    for paper in daily_papers:
        paper_data = paper.get("paper", {})
        paper_id = paper_data.get("id", "")
        if paper_id and paper_id not in seen_ids:
            seen_ids.add(paper_id)
            merged.append(paper)

    for paper in submitted_papers:
        paper_id = paper.get("id", "")
        if paper_id and paper_id not in seen_ids:
            seen_ids.add(paper_id)
            merged.append({"paper": paper})

    return merged
