"""Analysis component exposing content and cross-source capabilities."""

from dataclasses import dataclass

from app.services.analysis.content_analyzer import ContentAnalyzer
from app.services.analysis.cross_source_analyzer import CrossSourceAnalyzer
from app.services.analysis.models import (
    ContentAnalysisResult,
    CrossSourceCoverage,
    CrossSourceGroup,
    DiscoveredPattern,
    PatternSnapshot,
)
from app.services.analysis.pattern_discoverer import PatternDiscoverer


@dataclass(frozen=True)
class AnalysisService:
    """Compose analyzers while preserving the existing content-analysis API."""

    content: ContentAnalyzer
    cross_source: CrossSourceAnalyzer
    patterns: PatternDiscoverer

    async def analyze(self, knowledge_id: str) -> ContentAnalysisResult:
        """Analyze one item using the existing content analyzer."""
        return await self.content.analyze(knowledge_id)

    async def analyze_batch(
        self, limit: int = 50, *, raise_on_error: bool = False
    ) -> list[ContentAnalysisResult]:
        """Analyze a bounded batch; optionally fail the run on partial failures."""
        return await self.content.analyze_batch(limit, raise_on_error=raise_on_error)

    def find_groups(self, time_window_days: int = 7) -> list[CrossSourceGroup]:
        """Compute and persist cross-source groups for a window without LLM calls.

        Called by the analysis pipeline; no automatic scheduler registration.
        Async callers must use asyncio.to_thread for this blocking operation.
        """
        return self.cross_source.find_groups(time_window_days)

    def find_coverage(self, topic: str, time_window_days: int = 7) -> CrossSourceCoverage:
        """Read coverage for a theme or typed entity."""
        return self.cross_source.find_coverage(topic, time_window_days)

    def discover_patterns(self, time_window_days: int = 30) -> list[DiscoveredPattern]:
        """Detect and persist patterns using the shared provider budget.

        Called by the analysis pipeline; no automatic scheduler registration.
        Database I/O and LLM requests are synchronous. Async callers must use
        asyncio.to_thread for the complete call to avoid blocking the event loop.
        """
        return self.patterns.discover_patterns(time_window_days)

    def get_pattern_history(self, pattern_id: str) -> list[PatternSnapshot]:
        """Read daily pattern observations."""
        return self.patterns.get_pattern_history(pattern_id)
