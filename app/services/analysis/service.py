"""Analysis component exposing content and cross-source capabilities."""

from dataclasses import dataclass

from app.services.analysis.content_analyzer import ContentAnalyzer
from app.services.analysis.cross_source_analyzer import CrossSourceAnalyzer
from app.services.analysis.models import (
    ContentAnalysisResult,
    CrossSourceCoverage,
    CrossSourceGroup,
)


@dataclass(frozen=True)
class AnalysisService:
    """Compose analyzers while preserving the existing content-analysis API."""

    content: ContentAnalyzer
    cross_source: CrossSourceAnalyzer

    async def analyze(self, knowledge_id: str) -> ContentAnalysisResult:
        """Analyze one item using the existing content analyzer."""
        return await self.content.analyze(knowledge_id)

    async def analyze_batch(self, limit: int = 50) -> list[ContentAnalysisResult]:
        """Preserve batch callers such as scripts/update_knowledge.py."""
        return await self.content.analyze_batch(limit)

    def find_groups(self, time_window_days: int = 7) -> list[CrossSourceGroup]:
        """Compute and persist cross-source groups for a window."""
        return self.cross_source.find_groups(time_window_days)

    def find_coverage(self, topic: str, time_window_days: int = 7) -> CrossSourceCoverage:
        """Read coverage for a theme or typed entity."""
        return self.cross_source.find_coverage(topic, time_window_days)
