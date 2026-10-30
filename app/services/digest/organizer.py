"""Deterministic editorial organization of selected daily digest items."""

from app.services.digest.config import Category
from app.services.digest.models import DailyDigest, topic_groups

_SECTION_LAYOUT: dict[Category, tuple[int, str]] = {
    "papers": (0, "📄 Papers"),
    "github": (1, "💻 GitHub"),
    "news": (2, "📰 News"),
    "others": (3, "📦 Others"),
}
_SUMMARY_LIMIT = 200


class ContentOrganizer:
    """Pure, synchronous presentation step; no provider or persistence dependency.

    Selection, scores and intelligence stay unchanged. Empty sections are
    omitted, and topic references follow the resulting display order.
    """

    def organize(self, digest: DailyDigest) -> DailyDigest:
        """Return an independent, validated digest with stable editorial ordering.

        Sort items by descending importance, breaking ties by knowledge ID.
        Limit summaries to 200 Unicode code points, including the ellipsis.
        Repeated calls produce the same value without changing the input.
        """
        result = DailyDigest.model_validate(digest.model_dump())
        sections = sorted(
            (section for section in result.sections if section.items),
            key=lambda section: _SECTION_LAYOUT[section.category][0],
        )
        for section in sections:
            section.section_title = _SECTION_LAYOUT[section.category][1]
            section.items.sort(key=lambda item: (-item.importance_score, item.knowledge_id))
            for item in section.items:
                if len(item.summary) > _SUMMARY_LIMIT:
                    item.summary = item.summary[: _SUMMARY_LIMIT - 1].rstrip() + "…"
        result.sections = sections
        result.topic_groups = topic_groups(sections)
        return DailyDigest.model_validate(result.model_dump())
