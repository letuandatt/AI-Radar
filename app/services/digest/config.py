"""Digest selection policy reusing the canonical importance thresholds."""

from typing import Literal
from urllib.parse import quote

from pydantic import BaseModel, ConfigDict, Field

from app.config.importance import ImportanceConfig, Unit

Category = Literal["papers", "github", "news", "others"]


class DigestConfig(BaseModel):
    """Unknown sources are excluded unless an explicit Others threshold is supplied."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    importance: ImportanceConfig = Field(default_factory=ImportanceConfig)
    max_items_per_section: int = Field(default=5, ge=1, le=5, strict=True)
    others_threshold: Unit | None = None

    def selection(self, source_type: str, source_name: str) -> tuple[Category, float | None]:
        """Resolve the same exact source mapping as PriorityEvaluator."""
        label = f"{quote(source_type, safe='')}:{quote(source_name, safe='')}"
        category = (
            "github"
            if source_type == "github"
            else self.importance.digest_source_categories.get(label)
        )
        if category is None:
            return "others", self.others_threshold
        return category, {
            "papers": self.importance.threshold_papers,
            "github": self.importance.threshold_github,
            "news": self.importance.threshold_news,
        }[category]
