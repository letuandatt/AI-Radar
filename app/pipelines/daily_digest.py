"""Daily Intelligence Digest pipeline (D1).

Query candidates for a day -> Rank (C3) -> Select top N -> Synthesize a
markdown digest via the shared LLM chain -> deliver through a
NotificationChannel.

Independence rules (Wiring & Fix Plan D1):
- A digest failure NEVER re-ingests: insights live in the repository; only
  the delivery step is retried.
- The pipeline is delivered through a ``NotificationChannel`` seam —
  LogChannel today, ZaloChannel (S30) plugs in as one class.
"""

import asyncio
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Protocol, cast, runtime_checkable

from langchain_core.prompts import PromptTemplate
from pydantic import BaseModel

from app.core.logger import get_logger
from app.integrations.llm.provider import LLMProvider
from app.models.knowledge_object import KnowledgeObject
from app.prompts.loader import PromptLoader
from app.services.digest.ranker import DigestRanker, RankedDigestItem
from app.storage.knowledge.sqlite_store import SQLiteKnowledgeStore

logger = get_logger(__name__)

_PROMPT_NAME = "digest/daily"


class DigestDraft(BaseModel):
    """LLM-rendered digest body (markdown, no source links)."""

    markdown: str


class ChannelSendError(Exception):
    """Raised internally when a NotificationChannel reports failed delivery."""


@runtime_checkable
class NotificationChannel(Protocol):
    """Delivery seam for the rendered digest (D1).

    Implementations: LogChannel (now), ZaloChannel (S30), future web/email.
    """

    name: str

    def send(self, markdown: str) -> bool:
        """Deliver the digest. Returns True on success."""
        ...


class LogChannel:
    """Delivers the digest to the application log (default channel)."""

    name = "log"

    def send(self, markdown: str) -> bool:
        logger.info("Digest delivered via log channel:\n%s", markdown)
        return True


@dataclass(frozen=True)
class DigestResult:
    """Outcome of one digest run.

    ``sent=False`` means delivery failed — the markdown and ranked items
    are still present (insights are never lost); retrying means re-sending
    only.
    """

    target_date: date
    markdown: str
    items: list[RankedDigestItem] = field(default_factory=list)
    sent: bool = False
    channel: str = "log"
    error: str | None = None


class DigestQueryService:
    """Day-scoped candidate query over the repository.

    v1 filters ``get_all()`` in memory by ``fetched_at`` — fine for a
    personal-scale knowledge base; move to a SQL WHERE when the store grows.
    """

    def __init__(self, sqlite_store: SQLiteKnowledgeStore) -> None:
        self._store = sqlite_store

    def candidates_for_day(self, target_date: date) -> list[KnowledgeObject]:
        """KnowledgeObjects fetched within [00:00, next day) UTC."""
        window_start = datetime(
            target_date.year, target_date.month, target_date.day, tzinfo=timezone.utc
        )
        window_end = window_start + timedelta(days=1)

        candidates: list[KnowledgeObject] = []
        for ko in self._store.get_all():
            fetched_at = ko.fetched_at
            if fetched_at is None:
                continue
            if fetched_at.tzinfo is None:
                fetched_at = fetched_at.replace(tzinfo=timezone.utc)
            if window_start <= fetched_at < window_end:
                candidates.append(ko)

        logger.info("Digest query %s: %d candidates", target_date.isoformat(), len(candidates))
        return candidates


class DailyDigestPipeline:
    """One digest cycle: query -> rank -> synthesize -> deliver."""

    def __init__(
        self,
        sqlite_store: SQLiteKnowledgeStore,
        llm_provider: LLMProvider,
        ranker: DigestRanker | None = None,
        channel: NotificationChannel | None = None,
        max_items: int = 10,
    ) -> None:
        self._query = DigestQueryService(sqlite_store)
        self._ranker = ranker or DigestRanker()
        self._channel: NotificationChannel = channel or LogChannel()
        self._llm = llm_provider
        self._max_items = max_items
        self._prompt_template = PromptLoader().load(_PROMPT_NAME)
        self._prompt = PromptTemplate(
            template=self._prompt_template,
            input_variables=["insights", "day"],
        )

    def run(self, target_date: date | None = None) -> DigestResult:
        """Produce and deliver the digest for ``target_date`` (default: yesterday).

        Returns:
            DigestResult — ``sent`` False on delivery failure; markdown and
            items remain populated so a retry only re-sends. Delivery
            failures are reported via ``DigestResult.error`` (the caller
            decides how to surface them, e.g. a non-zero exit code).
        """
        day = target_date or (date.today() - timedelta(days=1))

        candidates = self._query.candidates_for_day(day)
        ranked = self._ranker.rank(candidates)
        top = ranked[: self._max_items]

        if not top:
            logger.info("Digest %s: no candidates — empty digest, nothing to send", day)
            return DigestResult(
                target_date=day, markdown="", items=[], sent=True, channel=self._channel.name
            )

        markdown = asyncio.run(self._synthesize(day, top))
        markdown += self._render_sources(top)

        sent = False
        error: str | None = None
        try:
            sent = bool(self._channel.send(markdown))
            if not sent:
                raise ChannelSendError(f"{self._channel.name} returned failure")
        except Exception as e:
            error = str(e)
            logger.error(
                "Digest delivery FAILED via %s: %s — insights remain in the "
                "repository; a retry re-sends only",
                self._channel.name,
                e,
            )

        logger.info(
            "Digest %s: %d items, sent=%s (channel=%s)",
            day.isoformat(),
            len(top),
            sent,
            self._channel.name,
        )
        return DigestResult(
            target_date=day,
            markdown=markdown,
            items=top,
            sent=sent,
            channel=self._channel.name,
            error=error,
        )

    async def _synthesize(self, day: date, top: list[RankedDigestItem]) -> str:
        """Render the digest body via the shared LLM chain (to_thread)."""
        insights_text = "\n".join(
            f"{i}. ({item.knowledge_object.source_type}, score={item.score}) "
            f"{item.knowledge_object.title} — {item.knowledge_object.metadata.summary}"
            for i, item in enumerate(top, start=1)
        )
        prompt_text = self._prompt.format(insights=insights_text, day=day.isoformat())

        draft = cast(
            DigestDraft,
            await asyncio.to_thread(self._llm.structured_chat, prompt_text, DigestDraft),
        )
        if not draft.markdown.strip():
            raise ValueError("LLM returned an empty digest")
        return draft.markdown.strip()

    @staticmethod
    def _render_sources(top: list[RankedDigestItem]) -> str:
        """Append the source list — appended by code, never trusted to the LLM."""
        lines = ["", "## Nguồn", ""]
        for item in top:
            ko = item.knowledge_object
            lines.append(f"- [{ko.title}]({ko.source_url}) — {ko.source_name}")
        return "\n".join(lines) + "\n"
