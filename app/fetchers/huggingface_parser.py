"""Hugging Face Data Parser implementation.

This module provides the concrete implementation for parsing data
from raw Hugging Face content.
"""

from datetime import datetime

from app.core.logger import get_logger
from app.models.article import RawArticle
from app.models.source import HFSource, HFSourceType

logger = get_logger(__name__)


class HuggingFaceParser:
    """Parses JSON metadata from Hugging Face API into RawArticle models.

    This parser handles the specific JSON structures returned by the
    Hugging Face Hub API for datasets and models, transforming them into
    the standardized RawArticle format for knowledge extraction.
    """

    def parse(self, data: dict, source: HFSource) -> list[RawArticle]:
        """Parse Hugging Face metadata JSON into a list of RawArticle models.

        Note: Hugging Face API returns a single dictionary per resource,
        not a list. This method returns a list with 0 or 1 element for
        consistency with other parsers.

        Args:
            data: The metadata dictionary from Hugging Face API.
            source: The source configuration this data belongs to.

        Returns:
            A list containing 0 or 1 RawArticle instance.
        """
        resource_id = data.get("id") or data.get("modelId") or data.get("datasetId")

        # Defensive Parsing: Skip if essential identifier is missing
        if not resource_id:
            logger.warning(
                "Skipping HF resource from %s: missing 'id', 'modelId', or 'datasetId'", source.name
            )
            return []

        # Extract title (prefer cardData.title, fallback to resource_id)
        card_data = data.get("cardData") or {}
        title = card_data.get("title") or resource_id

        # Build URL based on source type
        if source.source_type == HFSourceType.DATASET:
            url = f"https://huggingface.co/datasets/{resource_id}"
        else:  # MODEL
            url = f"https://huggingface.co/{resource_id}"

        # Extract content (description)
        content = data.get("description") or card_data.get("description") or ""

        # Parse last modified date
        published_date = self._parse_iso_date(data.get("lastModified"))

        article = RawArticle(
            title=title,
            url=url,
            content=content,
            published_date=published_date,
            source_name=source.name,
        )

        logger.info("Parsed HF resource: %s (%s)", title, source.name)
        return [article]

    def _parse_iso_date(self, date_str: str | None) -> datetime | None:
        """Convert Hugging Face's ISO 8601 date string to a datetime object.

        Hugging Face returns dates like "2024-03-15T10:00:00.000Z".
        Python's fromisoformat() doesn't handle the 'Z' suffix until Python 3.11,
        so we replace it with '+00:00' for compatibility.
        """
        if not date_str:
            return None
        try:
            # Handle milliseconds and 'Z' suffix
            if date_str.endswith("Z"):
                date_str = date_str[:-1] + "+00:00"
            # Remove milliseconds if present (e.g., ".000")
            if "." in date_str:
                date_str = date_str.split(".")[0] + date_str[date_str.rfind("+") :]
            return datetime.fromisoformat(date_str)
        except ValueError as error:
            logger.warning("Failed to parse date '%s': %s", date_str, error)
            return None

    def parse_daily_papers(
        self, data: list[dict], source_name: str = "hf-daily-papers"
    ) -> list[RawArticle]:
        """Parse HuggingFace Daily Papers into RawArticle models.

        Args:
            data: List of paper dictionaries from daily_papers API.
            source_name: Name to use for source_name field.

        Returns:
            List of parsed RawArticle instances.
        """
        articles: list[RawArticle] = []

        for paper in data:
            # Daily papers API structure
            paper_data = paper.get("paper", {})
            paper_id = paper_data.get("id") or paper.get("paper_id", "")
            title = paper_data.get("title", "")
            summary = paper_data.get("summary", "")

            if not paper_id or not title:
                logger.warning("Skipping daily paper: missing id or title")
                continue

            # Build URL
            url = f"https://huggingface.co/papers/{paper_id}"

            # Build content with paper metadata
            authors = paper_data.get("authors", [])
            author_names = [
                a.get("name", "") if isinstance(a, dict) else str(a) for a in authors[:5]
            ]

            content_parts = [
                f"Title: {title}",
                f"URL: {url}",
                f"Authors: {', '.join(author_names)}" if author_names else "",
                f"Summary: {summary}",
            ]

            # Add upvotes if available
            upvotes = paper.get("paper_upvotes", 0)
            if upvotes:
                content_parts.append(f"Upvotes: {upvotes}")

            content = "\n".join(part for part in content_parts if part)

            # Parse published date
            published_str = paper_data.get("published") or paper.get("published_at")
            published_date = self._parse_iso_date(published_str)

            articles.append(
                RawArticle(
                    title=title,
                    url=url,
                    content=content,
                    published_date=published_date,
                    source_name=source_name,
                )
            )

        logger.info("Parsed %d daily papers", len(articles))
        return articles

    def parse_trending_models(
        self, data: list[dict], source_name: str = "hf-trending"
    ) -> list[RawArticle]:
        """Parse trending models/datasets into RawArticle models.

        Args:
            data: List of model/dataset dictionaries.
            source_name: Name to use for source_name field.

        Returns:
            List of parsed RawArticle instances.
        """
        articles: list[RawArticle] = []

        for item in data:
            model_id = item.get("id") or item.get("modelId") or item.get("datasetId", "")
            if not model_id:
                continue

            # Determine type and build URL
            if "datasetId" in item or source_name == "hf-trending-datasets":
                url = f"https://huggingface.co/datasets/{model_id}"
                item_type = "dataset"
            else:
                url = f"https://huggingface.co/{model_id}"
                item_type = "model"

            # Extract title
            card_data = item.get("cardData") or {}
            title = card_data.get("title") or model_id

            # Extract description
            description = item.get("description") or card_data.get("description") or ""

            # Build content
            likes = item.get("likes", 0)
            downloads = item.get("downloads", 0)
            tags = item.get("tags", [])
            pipeline_tag = item.get("pipeline_tag", "")

            content_parts = [
                f"Title: {title}",
                f"URL: {url}",
                f"Type: {item_type}",
            ]
            if pipeline_tag:
                content_parts.append(f"Pipeline: {pipeline_tag}")
            if description:
                content_parts.append(f"Description: {description}")
            content_parts.append(f"Likes: {likes}")
            content_parts.append(f"Downloads: {downloads}")
            if tags:
                content_parts.append(f"Tags: {', '.join(tags[:10])}")

            content = f"Model: {model_id}\nLikes: {likes}\nDownloads: {downloads}".join(
                content_parts
            )

            published_date = self._parse_iso_date(item.get("lastModified"))

            articles.append(
                RawArticle(
                    title=f"[{item_type.title()}] {title}",
                    url=url,
                    content=content,
                    published_date=published_date,
                    source_name=source_name,
                )
            )

        logger.info("Parsed %d trending items from %s", len(articles), source_name)
        return articles

    def parse_papers_by_date(
        self, data: list[dict], source_name: str = "hf-papers"
    ) -> list[RawArticle]:
        """Parse HuggingFace papers (by date) into RawArticle models.

        Structure is similar to daily papers but with slight differences
        in field names depending on the API version.

        Args:
            data: List of paper dictionaries from papers API.
            source_name: Name to use for source_name field.

        Returns:
            List of parsed RawArticle instances.
        """
        articles: list[RawArticle] = []

        for paper in data:
            # Papers API structure: {"id": "...", "title": "...", "summary": "...", ...}
            paper_id = paper.get("id", "")
            title = paper.get("title", "")
            summary = paper.get("summary", "")

            if not paper_id or not title:
                logger.warning("Skipping paper: missing id or title")
                continue

            # Build URL
            url = f"https://huggingface.co/papers/{paper_id}"

            # Extract authors
            authors = paper.get("authors", [])
            author_names = []
            for a in authors[:5]:
                if isinstance(a, dict):
                    author_names.append(a.get("name", ""))
                elif isinstance(a, str):
                    author_names.append(a)

            # Build content
            content_parts = [
                f"Title: {title}",
                f"URL: {url}",
            ]
            if author_names:
                content_parts.append(f"Authors: {', '.join(author_names)}")
            if summary:
                content_parts.append(f"Summary: {summary}")

            # Add upvotes if available
            upvotes = paper.get("upvotes", 0)
            if upvotes:
                content_parts.append(f"Upvotes: {upvotes}")

            content = "\n".join(content_parts)

            # Parse published date
            published_str = paper.get("publishedAt") or paper.get("published")
            published_date = self._parse_iso_date(published_str)

            articles.append(
                RawArticle(
                    title=title,
                    url=url,
                    content=content,
                    published_date=published_date,
                    source_name=source_name,
                )
            )

        logger.info("Parsed %d papers by date", len(articles))
        return articles
