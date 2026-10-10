"""Run content analysis, cross-source grouping and temporal discovery in order."""

import asyncio
from typing import Any

from pydantic import BaseModel

from app.services.analysis.models import (
    ContentAnalysisResult,
    CrossSourceGroup,
    DiscoveredPattern,
)
from app.services.analysis.service import AnalysisService


class AnalysisRunResult(BaseModel):
    """Results from one completed run; each stage persists independently."""

    content: list[ContentAnalysisResult]
    groups: list[CrossSourceGroup]
    patterns: list[DiscoveredPattern]


async def run_analysis(
    service: AnalysisService,
    *,
    limit: int = 50,
    group_days: int = 7,
    pattern_days: int = 30,
    skip_content: bool = False,
    metrics: dict[str, Any] | None = None,
) -> AnalysisRunResult:
    """Run one bounded content batch, then aggregate the repository's windows.

    A content failure stops downstream stages after in-flight items finish.
    Completed stages remain saved if a later stage fails. The limit applies
    only to new content analyses, not group/pattern inputs or LLM descriptions.
    Empty results are valid. Synchronous aggregation runs off the event loop.
    """
    for name, value, minimum in (
        ("limit", limit, 1),
        ("group_days", group_days, 1),
        ("pattern_days", pattern_days, 7),
    ):
        if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
            raise ValueError(f"{name} must be an integer >= {minimum}")

    fields = metrics if metrics is not None else {}
    fields.update(analysis_stage="content", content_skipped=skip_content)

    content = [] if skip_content else await service.analyze_batch(limit, raise_on_error=True)
    fields.update(analyzed_items=len(content), analysis_stage="cross_source")

    groups = await asyncio.to_thread(service.find_groups, group_days)
    fields.update(cross_source_groups_returned=len(groups), analysis_stage="patterns")

    patterns = await asyncio.to_thread(service.discover_patterns, pattern_days)
    fields.update(patterns_discovered=len(patterns), analysis_stage="complete")

    return AnalysisRunResult(content=content, groups=groups, patterns=patterns)
