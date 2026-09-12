"""BM25 Keyword Index for Fusion Retrieval.

Implements keyword-based search using the BM25 algorithm (rank_bm25 library).
"""

import pickle
import re
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from rank_bm25 import BM25Okapi  # type: ignore[import-untyped]

from app.core.logger import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class BM25Document:
    """A document in the BM25 index."""

    id: str
    text: str
    content_hash: str
    published_at: datetime | None = None


@dataclass(frozen=True)
class BM25Result:
    """A single BM25 search result."""

    doc_id: str
    score: float


def tokenize(text: str) -> list[str]:
    """Simple tokenizer: lowercase, extract alphanumeric tokens >= 2 chars."""
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    return [t for t in tokens if len(t) >= 2]


class BM25Index:
    """BM25 keyword index backed by rank_bm25.

    Args:
        index_path: Path to save/load the index pickle file.
    """

    def __init__(self, index_path: str | Path | None = None) -> None:
        self._index_path = Path(index_path) if index_path else None
        self._documents: dict[str, BM25Document] = {}
        self._doc_ids: list[str] = []
        self._bm25: BM25Okapi | None = None
        self._lock = threading.RLock()

    @property
    def document_count(self) -> int:
        """Return the number of documents in the index."""
        return len(self._documents)

    @property
    def index_path(self) -> Path | None:
        """Return the index file path."""
        return self._index_path

    # ------------------------------------------------------------------
    # Build & Rebuild
    # ------------------------------------------------------------------

    def build(self, documents: list[BM25Document]) -> int:
        """Build the BM25 index from a list of documents.

        Applies global deduplication (GAP-005).

        Args:
            documents: List of BM25Documents to index.

        Returns:
            Number of documents indexed after deduplication.
        """
        with self._lock:
            deduped, duplicates_removed = self._deduplicate(documents)

            if duplicates_removed > 0:
                logger.info(
                    "BM25 deduplication: removed %d duplicate documents",
                    duplicates_removed,
                )

            self._documents = {doc.id: doc for doc in deduped}
            self._rebuild_bm25_unlocked()

            logger.info(
                "BM25 index built: %d documents (%d duplicates removed)",
                len(self._documents),
                duplicates_removed,
            )

            return len(self._documents)

    def _rebuild_bm25_unlocked(self) -> None:
        """Rebuild BM25Okapi from current documents. Caller must hold lock."""
        if not self._documents:
            self._bm25 = None
            self._doc_ids = []
            return

        self._doc_ids = list(self._documents.keys())
        corpus = [tokenize(self._documents[doc_id].text) for doc_id in self._doc_ids]

        valid_pairs = [(doc_id, tokens) for doc_id, tokens in zip(self._doc_ids, corpus) if tokens]

        if not valid_pairs:
            self._bm25 = None
            self._doc_ids = []
            return

        self._doc_ids = [doc_id for doc_id, _ in valid_pairs]
        valid_corpus = [tokens for _, tokens in valid_pairs]

        self._bm25 = BM25Okapi(valid_corpus)

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(self, query: str, top_k: int = 10) -> list[BM25Result]:
        """Search the BM25 index.

        BM25 is used for ranking, while lexical token matching determines
        whether a document is relevant. A document must contain all query
        tokens to be returned.

        Args:
            query: Search query string.
            top_k: Maximum number of results to return.

        Returns:
            List of BM25Result sorted by BM25 score descending.
        """
        with self._lock:
            if self._bm25 is None or not self._doc_ids:
                return []

            query_tokens = tokenize(query)
            if not query_tokens:
                return []

            query_token_set = set(query_tokens)

            scores = self._bm25.get_scores(query_tokens)

            # BM25 score alone is not a reliable relevance filter.
            # rank_bm25 can legitimately produce zero/negative scores
            # for matching terms depending on corpus statistics.
            candidate_indices = [
                i
                for i, doc_id in enumerate(self._doc_ids)
                if query_token_set.issubset(set(tokenize(self._documents[doc_id].text)))
            ]

            if not candidate_indices:
                return []

            candidate_indices.sort(
                key=lambda i: scores[i],
                reverse=True,
            )

            candidate_indices = candidate_indices[:top_k]

            return [
                BM25Result(
                    doc_id=self._doc_ids[i],
                    score=float(scores[i]),
                )
                for i in candidate_indices
            ]

    # ------------------------------------------------------------------
    # Incremental Update
    # ------------------------------------------------------------------

    def add_document(self, doc: BM25Document) -> None:
        """Add a single document to the index.

        Args:
            doc: Document to add.
        """
        with self._lock:
            self._documents[doc.id] = doc
            self._rebuild_bm25_unlocked()
            logger.debug("BM25: added document %s", doc.id)

    def remove_document(self, doc_id: str) -> bool:
        """Remove a document from the index by ID.

        Args:
            doc_id: The document ID to remove.

        Returns:
            True if removed, False if not found.
        """
        with self._lock:
            if doc_id not in self._documents:
                return False

            del self._documents[doc_id]
            self._rebuild_bm25_unlocked()
            logger.debug("BM25: removed document %s", doc_id)
            return True

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self, path: str | Path | None = None) -> Path:
        """Save the index to a pickle file."""
        save_path = Path(path) if path else self._index_path
        if save_path is None:
            raise ValueError("No index path specified for save")

        save_path.parent.mkdir(parents=True, exist_ok=True)

        with self._lock:
            with open(save_path, "wb") as f:
                pickle.dump(self._documents, f)

        logger.info("BM25 index saved to %s (%d docs)", save_path, len(self._documents))
        return save_path

    def load(self, path: str | Path | None = None) -> int:
        """Load the index from a pickle file."""
        load_path = Path(path) if path else self._index_path
        if load_path is None:
            raise ValueError("No index path specified for load")

        if not load_path.exists():
            raise FileNotFoundError(f"BM25 index file not found: {load_path}")

        with self._lock:
            with open(load_path, "rb") as f:
                self._documents = pickle.load(f)  # noqa: S301
            self._rebuild_bm25_unlocked()

        logger.info(
            "BM25 index loaded from %s (%d docs)",
            load_path,
            len(self._documents),
        )
        return len(self._documents)

    def get_all_document_ids(self) -> list[str]:
        """Return all document IDs in the index."""
        return list(self._documents.keys())

    # ------------------------------------------------------------------
    # Deduplication (GAP-005)
    # ------------------------------------------------------------------

    def _deduplicate(self, documents: list[BM25Document]) -> tuple[list[BM25Document], int]:
        """Deduplicate documents by content_hash, keeping the newest."""
        by_hash: dict[str, BM25Document] = {}
        duplicates_removed = 0

        for doc in documents:
            if doc.content_hash in by_hash:
                existing = by_hash[doc.content_hash]
                if self._is_newer(doc, existing):
                    by_hash[doc.content_hash] = doc
                duplicates_removed += 1
            else:
                by_hash[doc.content_hash] = doc

        return list(by_hash.values()), duplicates_removed

    @staticmethod
    def _is_newer(candidate: BM25Document, existing: BM25Document) -> bool:
        """Check if candidate is newer than existing."""
        if candidate.published_at is None:
            return False
        if existing.published_at is None:
            return True
        return candidate.published_at > existing.published_at
