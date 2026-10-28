"""Batch modes, limits, reports and cleanup without external services."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.processing_result import ProcessingResult
from app.pipelines.analysis import AnalysisRunResult
from scripts.update_knowledge import main


@pytest.fixture
def runtime(monkeypatch, tmp_path):
    from app.config import settings as config
    from app.pipelines import analysis, knowledge_update
    from app.services.repository import bootstrap

    settings = SimpleNamespace(
        sqlite_path=tmp_path / "knowledge.db",
        run_metrics_path=tmp_path / "runs.jsonl",
        llm_primary_provider="ollama",
    )
    monkeypatch.setattr(config, "get_settings", lambda: settings)
    repository = MagicMock()
    init = MagicMock(return_value=repository)
    chain = MagicMock(cost_tracker=None)
    factory = MagicMock(return_value=chain)
    processing = MagicMock()
    builder = MagicMock(return_value=processing)
    processor = MagicMock(return_value=ProcessingResult(total_input=1, processing_duration=0))
    service = MagicMock()
    analysis_factory = MagicMock(return_value=service)
    runner = AsyncMock(return_value=AnalysisRunResult(content=[], groups=[], patterns=[]))
    monkeypatch.setattr(bootstrap, "initialize_knowledge_repository", init)
    monkeypatch.setattr(bootstrap, "create_llm_chain", factory)
    monkeypatch.setattr(bootstrap, "create_analysis_service", analysis_factory)
    monkeypatch.setattr(knowledge_update, "build_processing_pipeline", builder)
    monkeypatch.setattr(knowledge_update, "run_knowledge_update", processor)
    monkeypatch.setattr(analysis, "run_analysis", runner)
    return SimpleNamespace(**locals())


def test_analysis_only_skips_acquisition_processing_and_writes_empty_success(runtime, tmp_path):
    report = tmp_path / "report.json"
    assert main(["--analysis-only", "--limit", "3", "--report", str(report)]) == 0
    runtime.builder.assert_not_called()
    runtime.processor.assert_not_called()
    runtime.analysis_factory.assert_called_once_with(runtime.repository, runtime.chain)
    assert runtime.runner.call_args.kwargs["limit"] == 3
    runtime.repository.shutdown.assert_called_once()
    payload = json.loads(report.read_text())
    assert payload["metrics"]["status"] == "success"
    assert payload["analysis"] == {"content": [], "groups": [], "patterns": []}


@pytest.mark.parametrize("stage", ["chain", "analysis"])
def test_failure_closes_repository_and_records_failed_status(runtime, tmp_path, stage):
    if stage == "chain":
        runtime.factory.side_effect = RuntimeError("bootstrap failed")
    else:
        runtime.runner.side_effect = RuntimeError("LLM failed")
    report = tmp_path / "failure.json"
    assert main(["--analysis-only", "--report", str(report)]) == 1
    runtime.repository.shutdown.assert_called_once()
    payload = json.loads(report.read_text())
    assert payload["metrics"]["status"] == "failed"
    assert payload["analysis"] is None
    assert len(runtime.settings.run_metrics_path.read_text().splitlines()) == 1


def raw_article(index):
    return dict(
        title=f"AI article {index}",
        content="AI research " * 30,
        url=f"https://example.com/{index}",
        source_name="rss",
        published_date="2026-10-10T00:00:00Z",
    )


def test_cached_input_limits_after_dedup_and_shares_provider(runtime, tmp_path):
    path = tmp_path / "raw.json"
    path.write_text(json.dumps([raw_article(1), raw_article(1), raw_article(2), raw_article(3)]))
    assert main(["--input-json", str(path), "--max-articles", "2"]) == 0
    runtime.builder.assert_called_once_with(runtime.repository, runtime.settings, runtime.chain)
    acquired = runtime.processor.call_args.args[0]
    assert len(acquired.articles) == 2
    assert [a.url for a in acquired.articles] == ["https://example.com/1", "https://example.com/2"]
    assert acquired.total_articles == 4
    runtime.analysis_factory.assert_called_once_with(runtime.repository, runtime.chain)


def test_bad_cached_input_fails_before_bootstrap(runtime, tmp_path):
    path = tmp_path / "raw.json"
    path.write_text('[{"title":"incomplete"}]')
    assert main(["--input-json", str(path)]) == 1
    runtime.init.assert_not_called()
    runtime.factory.assert_not_called()


def test_processing_failure_is_reported_as_partial(runtime, tmp_path):
    path = tmp_path / "raw.json"
    path.write_text(json.dumps([raw_article(1)]))
    runtime.processor.return_value = ProcessingResult(
        total_input=1, processing_duration=0, failed_objects=1
    )
    assert main(["--input-json", str(path)]) == 1
    runtime.runner.assert_awaited_once()
    payload = json.loads(runtime.settings.run_metrics_path.read_text())
    assert payload["metrics"]["status"] == "partial"


def test_dry_run_reads_no_input_and_bootstraps_nothing(runtime, tmp_path):
    assert main(["--input-json", str(tmp_path / "missing.json"), "--dry-run"]) == 0
    runtime.init.assert_not_called()
    assert not runtime.settings.run_metrics_path.exists()


@pytest.mark.parametrize(
    "args",
    [
        ["--limit", "0"],
        ["--pattern-days", "6"],
        ["--skip-content"],
        ["--analysis-only", "--max-articles", "1"],
    ],
)
def test_invalid_arguments_never_initialize(runtime, args):
    with pytest.raises(SystemExit) as error:
        main(args)
    assert error.value.code == 2
    runtime.init.assert_not_called()
