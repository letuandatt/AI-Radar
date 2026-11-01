"""Manual adds persist through the real application facade with mocked providers."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.core.utils import compute_text_hash
from app.models.metadata import ExtractionResult
from app.services.app_service import ApplicationService
from app.services.knowledge.manual_add_service import ManualAddService
from app.services.knowledge.models import ManualAddError, ManualAddRequest
from app.services.knowledge.url_fetcher import FetchedPage, FetchError
from app.services.repository.access_service import RepositoryAccessService
from app.storage.knowledge.sqlite_store import SQLiteKnowledgeStore
from app.storage.search.bm25_index import BM25Index


@pytest.fixture
def wired(tmp_path):
    store = SQLiteKnowledgeStore(str(tmp_path / "manual.db"))
    bm25 = BM25Index()
    access = RepositoryAccessService(store)
    app = ApplicationService(
        SimpleNamespace(
            sqlite_store=store, qdrant_store=Mock(), embedding_provider=Mock(), bm25_index=bm25
        ),
        access,
        Mock(),
    )
    app._sync_vector_with_retry = Mock(return_value=True)
    extractor = SimpleNamespace(
        extract_single=AsyncMock(
            return_value=ExtractionResult(
                summary="A research summary",
                topics=["AI"],
                entities=["Research lab"],
                relevance_score=0.8,
            )
        )
    )
    analyzer = SimpleNamespace(analyze=AsyncMock())
    scorer = SimpleNamespace(score_batch=Mock())
    fetcher = SimpleNamespace(
        fetch=AsyncMock(
            return_value=FetchedPage(
                "https://example.org/article",
                "A research article",
                "Useful research content. " * 10,
                False,
            )
        )
    )
    service = ManualAddService(app, access, fetcher, extractor, analyzer, scorer)
    yield SimpleNamespace(
        service=service,
        store=store,
        app=app,
        access=access,
        extractor=extractor,
        analyzer=analyzer,
        scorer=scorer,
        fetcher=fetcher,
        bm25=bm25,
    )
    store.close()


async def test_add_runs_existing_pipeline_and_saves_consistent_identity(wired):
    result = await wired.service.add(ManualAddRequest(url="https://example.org/article"))
    obj = wired.store.get_by_id(result.knowledge_id)
    assert result.status == "created" and result.indexing == "ready"
    assert result.analysis == result.importance == "ready"
    assert obj.content_hash == compute_text_hash(obj.content_text)
    assert obj.source_type == "manual" and obj.published_at is None
    assert wired.bm25.search("research", top_k=1)[0].doc_id == obj.id
    wired.analyzer.analyze.assert_awaited_once_with(obj.id)
    wired.scorer.score_batch.assert_called_once_with([obj.id])
    assert wired.app._sync_vector_with_retry.call_args.args[0].id == obj.id


async def test_repeat_skips_network_and_llm_and_does_not_overwrite_title(wired):
    first = await wired.service.add(ManualAddRequest(url="https://example.org/article"))
    again = await wired.service.add(
        ManualAddRequest(url="https://example.org/article#part", title="Other")
    )
    assert again.knowledge_id == first.knowledge_id and again.status == "existing"
    assert again.analysis == "unchanged" and wired.store.count() == 1
    wired.fetcher.fetch.assert_awaited_once()
    wired.extractor.extract_single.assert_awaited_once()
    assert wired.store.get_by_id(first.knowledge_id).title == "A research article"


async def test_duplicate_content_reuses_original_object(wired):
    first = await wired.service.add(ManualAddRequest(url="https://example.org/article"))
    wired.fetcher.fetch.return_value = FetchedPage(
        "https://example.org/mirror", "Mirror", "Useful research content. " * 10, False
    )
    again = await wired.service.add(ManualAddRequest(url="https://example.org/mirror"))
    assert again.knowledge_id == first.knowledge_id and again.status == "existing"
    assert wired.store.count() == 1
    wired.extractor.extract_single.assert_awaited_once()


async def test_deleted_item_is_not_resurrected(wired):
    first = await wired.service.add(ManualAddRequest(url="https://example.org/article"))
    wired.store.delete_by_id(first.knowledge_id)
    with pytest.raises(ManualAddError) as error:
        await wired.service.add(ManualAddRequest(url="https://example.org/article"))
    assert error.value.status == 409 and wired.store.count() == 0


@pytest.mark.parametrize("stage", ["fetch", "extract", "save"])
async def test_failure_before_save_does_not_create_an_object(wired, stage):
    if stage == "fetch":
        wired.fetcher.fetch.side_effect = FetchError("Blocked URL")
    elif stage == "extract":
        wired.extractor.extract_single.side_effect = RuntimeError("provider secret")
    else:
        wired.app.save_objects = Mock(side_effect=RuntimeError("database secret"))
    with pytest.raises(ManualAddError) as error:
        await wired.service.add(ManualAddRequest(url="https://example.org/article"))
    assert "secret" not in str(error.value)
    assert wired.store.count() == 0
    wired.analyzer.analyze.assert_not_awaited()


@pytest.mark.parametrize("stage", ["index", "analysis", "importance"])
async def test_after_save_failures_return_saved_id_and_explicit_outcome(wired, stage):
    if stage == "index":
        wired.app._sync_vector_with_retry.return_value = False
    elif stage == "analysis":
        wired.analyzer.analyze.side_effect = RuntimeError("provider secret")
    else:
        wired.scorer.score_batch.side_effect = RuntimeError("provider secret")
    result = await wired.service.add(ManualAddRequest(url="https://example.org/article"))
    assert wired.store.get_by_id(result.knowledge_id) is not None
    assert "secret" not in result.model_dump_json()
    if stage == "index":
        assert result.indexing == "partial"
    elif stage == "analysis":
        assert result.analysis == "failed" and result.importance == "skipped"
        wired.scorer.score_batch.assert_not_called()
    else:
        assert result.analysis == "ready" and result.importance == "failed"


async def test_busy_request_does_not_start_another_fetch(wired):
    entered, release = asyncio.Event(), asyncio.Event()
    page = wired.fetcher.fetch.return_value

    async def paused(url):
        entered.set()
        await release.wait()
        return page

    wired.fetcher.fetch.side_effect = paused
    task = asyncio.create_task(
        wired.service.add(ManualAddRequest(url="https://example.org/article"))
    )
    await entered.wait()
    with pytest.raises(ManualAddError) as error:
        await wired.service.add(ManualAddRequest(url="https://example.org/other"))
    assert error.value.status == 409
    release.set()
    await task
    wired.fetcher.fetch.assert_awaited_once()
