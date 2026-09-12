"""Contextual Chunk Headers (CCH) Builder.

Builds context headers for embedding to improve disambiguation.
"""

from datetime import datetime

from app.core.logger import get_logger
from app.models.knowledge_object import KnowledgeObject

logger = get_logger(__name__)


class ContextBuilder:
    """Builds Contextual Chunk Headers for KnowledgeObjects.

    CCH format:
    [Source: {source_name}| Type: {source_type}| Date: {published_at}| Topics: {topics}]
    {content_text}

    This helps embedding models distinguish context (e.g., "pipeline" in NLP vs DevOps).

    Args:
        max_header_chars: Maximum characters for header (default: 200).
    """

    def __init__(self, max_header_chars: int = 200) -> None:
        self._max_header_chars = max_header_chars

    def build_header(self, knowledge_object: KnowledgeObject) -> str:
        """Build CCH header for a KnowledgeObject.

        Args:
            knowledge_object: The object to build header for.

        Returns:
            Formatted header string.
        """
        source_name = knowledge_object.source_name
        source_type = knowledge_object.source_type
        published_at = self._format_date(knowledge_object.published_at)
        topics = ", ".join(knowledge_object.metadata.topics[:5])  # Limit to 5 topics

        header = (
            f"[Source: {source_name}| Type: {source_type}| Date: {published_at}| Topics: {topics}]"
        )

        # Truncate if too long
        if len(header) > self._max_header_chars:
            header = header[: self._max_header_chars - 3] + "..."
            logger.debug(
                "CCH header truncated from %d to %d chars",
                len(header) + 3,
                self._max_header_chars,
            )

        return header

    def build_for_embedding(self, knowledge_object: KnowledgeObject) -> str:
        """Build full text for embedding (CCH header + content).

        Args:
            knowledge_object: The object to build embedding text for.

        Returns:
            Formatted text with CCH header prepended.
        """
        header = self.build_header(knowledge_object)
        content = knowledge_object.content_text

        full_text = f"{header}\n{content}"
        return full_text

    def build_batch_for_embedding(self, knowledge_objects: list[KnowledgeObject]) -> list[str]:
        """Build embedding texts for a batch of KnowledgeObjects.

        Args:
            knowledge_objects: List of objects to build texts for.

        Returns:
            List of formatted texts with CCH headers.
        """
        return [self.build_for_embedding(obj) for obj in knowledge_objects]

    @staticmethod
    def _format_date(dt: datetime | None) -> str:
        """Format datetime for CCH header.

        Args:
            dt: Datetime to format.

        Returns:
            Formatted date string (YYYY-MM-DD) or "Unknown".
        """
        if dt is None:
            return "Unknown"
        return dt.strftime("%Y-%m-%d")
