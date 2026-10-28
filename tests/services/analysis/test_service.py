"""Analysis component delegation and bootstrap wiring without external services."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core import application
from app.services.analysis.service import AnalysisService
from app.services.repository import bootstrap


@pytest.mark.asyncio
async def test_component_preserves_content_api_and_exposes_cross_source():
    content = SimpleNamespace(analyze=AsyncMock(), analyze_batch=AsyncMock())
    cross = MagicMock()
    patterns = MagicMock()
    service = AnalysisService(content, cross, patterns)
    assert await service.analyze("ko-1") is content.analyze.return_value
    assert await service.analyze_batch() is content.analyze_batch.return_value
    content.analyze.assert_awaited_once_with("ko-1")
    content.analyze_batch.assert_awaited_once_with(50, raise_on_error=False)
    assert service.find_groups(30) is cross.find_groups.return_value
    assert service.find_coverage("rag", 30) is cross.find_coverage.return_value
    assert service.discover_patterns(30) is patterns.discover_patterns.return_value
    assert service.get_pattern_history("p1") is patterns.get_pattern_history.return_value
    patterns.discover_patterns.assert_called_once_with(30)
    patterns.get_pattern_history.assert_called_once_with("p1")
    cross.find_groups.assert_called_once_with(30)
    cross.find_coverage.assert_called_once_with("rag", 30)


def test_bootstrap_shares_access_and_provider_and_registry_returns_component(monkeypatch):
    content_factory = MagicMock()
    cross_factory = MagicMock()
    pattern_factory = MagicMock()
    monkeypatch.setattr(bootstrap, "PatternDiscoverer", pattern_factory)
    monkeypatch.setattr(bootstrap, "ContentAnalyzer", content_factory)
    monkeypatch.setattr(bootstrap, "CrossSourceAnalyzer", cross_factory)
    monkeypatch.setattr(bootstrap, "get_settings", lambda: SimpleNamespace(llm_max_concurrent=2))
    initializer = SimpleNamespace(sqlite_store=MagicMock())
    chain = MagicMock()
    service = bootstrap.create_analysis_service(initializer, chain, max_groups=5)
    assert isinstance(service, AnalysisService)
    content_args = content_factory.call_args.kwargs
    cross_factory.assert_called_once_with(content_args["access_service"], chain, max_groups=5)
    assert content_args["llm_provider"] is chain
    assert service.patterns is pattern_factory.return_value
    pattern_factory.assert_called_once_with(
        content_args["access_service"], chain, content_args["prompt_loader"]
    )
    assert service.content is content_factory.return_value
    assert service.cross_source is cross_factory.return_value

    registry = MagicMock()
    registry.get_component.side_effect = {"repository": initializer, "llm_chain": chain}.get
    monkeypatch.setattr(application, "_registry", registry)
    factory = MagicMock(return_value=service)
    monkeypatch.setattr(application, "create_analysis_service", factory)
    assert application._init_analysis() is service
    factory.assert_called_once_with(initializer, chain)
