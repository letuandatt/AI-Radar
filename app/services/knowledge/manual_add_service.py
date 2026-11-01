"""Add one public article through existing extraction, storage and analysis services."""

import asyncio
import logging
from datetime import datetime, timezone
from urllib.parse import urlsplit
from uuid import NAMESPACE_URL, uuid5

from app.core.utils import compute_text_hash
from app.models.enriched_article import EnrichedArticle
from app.models.knowledge_object import KnowledgeObject
from app.models.normalized_article import NormalizedArticle
from app.services.analysis.content_analyzer import ContentAnalyzer
from app.services.app_service import ApplicationService
from app.services.extraction.metadata_extractor import MetadataExtractor
from app.services.importance.scorer import ImportanceScorer
from app.services.knowledge.models import ManualAddError, ManualAddRequest, ManualAddResult
from app.services.knowledge.object_builder import ObjectBuilder
from app.services.knowledge.object_validator import KnowledgeObjectValidator
from app.services.knowledge.url_fetcher import FetchError, PublicPageFetcher
from app.services.repository.access_service import RepositoryAccessService

logger = logging.getLogger(__name__)


def manual_id(url: str) -> str:
    """Stable IDs keep resubmission consistent across SQLite and secondary indexes."""
    return str(uuid5(NAMESPACE_URL, f"ai-radar:manual:{url}"))


class ManualAddService:
    """One in-flight add per service; no queue and no acquisition/scheduler run.

    Existing records are returned without overwriting or rerunning paid analysis.
    Post-save failures are outcomes, not failed writes. Retry never resurrects trash.
    """

    def __init__(
        self,
        app: ApplicationService,
        access: RepositoryAccessService,
        fetcher: PublicPageFetcher,
        extractor: MetadataExtractor,
        analyzer: ContentAnalyzer,
        scorer: ImportanceScorer,
    ) -> None:
        self._app, self._access, self._fetcher = app, access, fetcher
        self._extractor, self._analyzer, self._scorer = extractor, analyzer, scorer
        self._lock = asyncio.Lock()

    async def _existing(
        self, identity: str, content_hash: str | None = None
    ) -> ManualAddResult | None:
        obj = await asyncio.to_thread(
            self._access.get_knowledge_object, identity, include_deleted=True
        )
        if (
            obj is not None
            and await asyncio.to_thread(self._app.get_knowledge_object, obj.id) is None
        ):
            raise ManualAddError(409, "This URL belongs to an item in trash")
        if obj is None and content_hash is not None:
            obj = await asyncio.to_thread(self._access.find_content_duplicate, content_hash)
        if obj is None:
            return None
        return ManualAddResult(
            knowledge_id=obj.id,
            status="existing",
            indexing="unchanged",
            analysis="unchanged",
            importance="unchanged",
        )

    async def add(self, request: ManualAddRequest) -> ManualAddResult:
        """Fetch, extract, persist, analyze and score; public errors contain no upstream text."""
        if self._lock.locked():
            raise ManualAddError(409, "Another article is being added; try again shortly")
        async with self._lock:
            existing = await self._existing(manual_id(request.url))
            if existing is not None:
                return existing
            logger.info("Manual add START: fetching public page")
            try:
                page = await self._fetcher.fetch(request.url)
            except FetchError as error:
                raise ManualAddError(422, str(error)) from error
            identity, content_hash = manual_id(page.url), compute_text_hash(page.text)
            existing = await self._existing(identity, content_hash)
            if existing is not None:
                return existing
            article = NormalizedArticle(
                article_id=compute_text_hash(page.url),
                url=page.url,
                title=request.title or page.title,
                content=page.text,
                source_type="manual",
                source_name=urlsplit(page.url).hostname or "manual",
                published_date=None,
                fetched_at=datetime.now(timezone.utc),
                raw_content_hash=content_hash,
            )
            logger.info("Manual add %s: extracting metadata", identity)
            try:
                metadata = await self._extractor.extract_single(article, 0, 1)
                obj: KnowledgeObject = ObjectBuilder().build(
                    [
                        EnrichedArticle(
                            article=article, extraction=metadata, extraction_status="success"
                        )
                    ]
                )[0]
                obj.id = identity
                if not KnowledgeObjectValidator().validate(obj).is_valid:
                    raise ValueError("Invalid extracted metadata")
            except Exception as error:
                logger.warning("Manual add metadata failed (%s)", type(error).__name__)
                raise ManualAddError(
                    503, "Metadata extraction failed; article was not saved"
                ) from error
            logger.info("Manual add %s: saving repository and indexes", identity)
            try:
                saved = await asyncio.to_thread(self._app.save_objects, [obj])
                indexed = saved.is_fully_consistent
            except Exception as error:
                # A write may have committed before a later operation failed.
                if await asyncio.to_thread(self._app.get_knowledge_object, identity) is None:
                    raise ManualAddError(
                        503, "Article could not be saved; please try again"
                    ) from error
                indexed = False
            if await asyncio.to_thread(self._app.get_knowledge_object, identity) is None:
                raise ManualAddError(
                    409, "Article is unavailable; check the collection before retrying"
                )
            result = ManualAddResult(
                knowledge_id=identity,
                status="created",
                indexing="ready" if indexed else "partial",
                analysis="failed",
                importance="skipped",
                content_truncated=page.truncated,
            )
            logger.info("Manual add %s: analyzing saved article", identity)
            try:
                await self._analyzer.analyze(identity)
                result.analysis = "ready"
            except Exception as error:
                logger.warning("Manual add analysis failed (%s)", type(error).__name__)
            if result.analysis == "ready":
                logger.info("Manual add %s: computing importance", identity)
                try:
                    await asyncio.to_thread(self._scorer.score_batch, [identity])
                    result.importance = "ready"
                except Exception as error:
                    result.importance = "failed"
                    logger.warning("Manual add importance failed (%s)", type(error).__name__)
            logger.info(
                "Manual add DONE: id=%s indexing=%s analysis=%s importance=%s",
                identity,
                result.indexing,
                result.analysis,
                result.importance,
            )
            return result
