"""Unit tests for BM25Index."""

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.storage.search.bm25_index import (
    BM25Document,
    BM25Index,
    tokenize,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def index(tmp_path: Path) -> BM25Index:
    """Create a BM25Index with a temporary path."""
    return BM25Index(index_path=tmp_path / "bm25_index.pkl")


def _make_doc(
    doc_id: str = "doc_001",
    text: str = "Test document content",
    content_hash: str | None = None,
    published_at: datetime | None = None,
) -> BM25Document:
    """Helper to create a BM25Document."""
    if content_hash is None:
        content_hash = f"hash_{doc_id}"
    return BM25Document(
        id=doc_id,
        text=text,
        content_hash=content_hash,
        published_at=published_at,
    )


# =============================================================================
# Tokenizer Tests
# =============================================================================


class TestTokenize:
    """Tests for the tokenize function."""

    def test_basic_tokenization(self) -> None:
        tokens = tokenize("Hello World")
        assert tokens == ["hello", "world"]

    def test_removes_short_tokens(self) -> None:
        tokens = tokenize("I am a test")
        assert tokens == ["am", "test"]

    def test_handles_special_characters(self) -> None:
        tokens = tokenize("vLLM v0.8.2 is fast!")
        assert "vllm" in tokens
        assert "v0" in tokens or "0" not in tokens  # version handling

    def test_empty_string(self) -> None:
        assert tokenize("") == []


# =============================================================================
# Build & Search Tests
# =============================================================================


class TestBM25BuildAndSearch:
    """Tests for build and search operations."""

    def test_build_from_documents(self, index: BM25Index) -> None:
        """Build index from 1000 documents."""
        docs = [_make_doc(doc_id=f"doc_{i}", text=f"Document about topic {i}") for i in range(1000)]

        count = index.build(docs)
        assert count == 1000
        assert index.document_count == 1000

    def test_search_returns_relevant(self, index: BM25Index) -> None:
        """Search returns documents matching the query."""
        docs = [
            _make_doc(doc_id="doc_1", text="OpenAI releases GPT-4o model"),
            _make_doc(doc_id="doc_2", text="Google announces Gemini update"),
            _make_doc(doc_id="doc_3", text="GPT-4o benchmark results published"),
        ]
        index.build(docs)

        results = index.search("GPT-4o", top_k=5)

        assert len(results) >= 2
        result_ids = {r.doc_id for r in results}
        assert "doc_1" in result_ids
        assert "doc_3" in result_ids

    def test_search_empty_index(self, index: BM25Index) -> None:
        """Search on empty index returns empty list."""
        results = index.search("anything")
        assert results == []

    def test_search_empty_query(self, index: BM25Index) -> None:
        """Search with empty query returns empty list."""
        docs = [_make_doc(text="Some content")]
        index.build(docs)

        results = index.search("")
        assert results == []

    def test_search_top_k_limit(self, index: BM25Index) -> None:
        """Search respects top_k parameter."""
        docs = [_make_doc(doc_id=f"doc_{i}", text="common search term") for i in range(20)]
        index.build(docs)

        results = index.search("common search term", top_k=5)
        assert len(results) <= 5

    def test_search_results_sorted_by_score(self, index: BM25Index) -> None:
        """Search results are sorted by score descending."""
        docs = [
            _make_doc(doc_id="doc_1", text="python python python programming language"),
            _make_doc(doc_id="doc_2", text="python programming tutorial guide"),
            _make_doc(doc_id="doc_3", text="java programming language tutorial"),
        ]
        index.build(docs)

        results = index.search("python programming")
        assert len(results) >= 2, f"Expected >= 2 results, got {len(results)}"

        scores = [r.score for r in results]
        assert scores == sorted(scores, reverse=True)


# =============================================================================
# Incremental Update Tests
# =============================================================================


class TestBM25IncrementalUpdate:
    """Tests for incremental add/remove operations."""

    def test_add_document(self, index: BM25Index) -> None:
        """Adding a document makes it searchable."""
        index.build(
            [
                _make_doc(doc_id="existing", text="existing document content"),
            ]
        )

        doc = _make_doc(doc_id="new_doc", text="brand new content here")
        index.add_document(doc)

        assert index.document_count == 2
        results = index.search("brand new content")
        assert len(results) == 1
        assert results[0].doc_id == "new_doc"

    def test_add_does_not_affect_existing(self, index: BM25Index) -> None:
        """Adding a document does not affect existing documents."""
        docs = [_make_doc(doc_id="existing", text="existing content here")]
        index.build(docs)

        index.add_document(_make_doc(doc_id="new", text="new content here"))

        results = index.search("existing content")
        assert len(results) == 1
        assert results[0].doc_id == "existing"

    def test_remove_document(self, index: BM25Index) -> None:
        """Removing a document makes it unsearchable."""
        docs = [
            _make_doc(doc_id="doc_1", text="first document"),
            _make_doc(doc_id="doc_2", text="second document"),
        ]
        index.build(docs)

        removed = index.remove_document("doc_1")
        assert removed is True
        assert index.document_count == 1

        results = index.search("first document")
        assert len(results) == 0

    def test_remove_nonexistent_document(self, index: BM25Index) -> None:
        """Removing a non-existent document returns False."""
        index.build([])
        assert index.remove_document("nonexistent") is False


# =============================================================================
# Deduplication Tests (GAP-005)
# =============================================================================


class TestBM25Deduplication:
    """Tests for global deduplication by content_hash."""

    def test_dedup_keeps_newest(self, index: BM25Index) -> None:
        """When two docs share content_hash, the newest is kept."""
        now = datetime.now(timezone.utc)
        older = now - timedelta(days=10)

        doc_old = _make_doc(
            doc_id="old_doc",
            text="Same content here",
            content_hash="same_hash",
            published_at=older,
        )
        doc_new = _make_doc(
            doc_id="new_doc",
            text="Same content here",
            content_hash="same_hash",
            published_at=now,
        )

        count = index.build([doc_old, doc_new])
        assert count == 1  # Only 1 after dedup

        # The kept document should be the newer one
        doc_ids = index.get_all_document_ids()
        assert doc_ids == ["new_doc"]

    def test_dedup_different_hashes_kept(self, index: BM25Index) -> None:
        """Documents with different content_hash are all kept."""
        doc1 = _make_doc(doc_id="doc_1", content_hash="hash_1")
        doc2 = _make_doc(doc_id="doc_2", content_hash="hash_2")

        count = index.build([doc1, doc2])
        assert count == 2

    def test_dedup_logs_duplicates(self, index: BM25Index, caplog) -> None:
        """Deduplication logs the number of duplicates removed."""
        doc1 = _make_doc(doc_id="doc_1", content_hash="same_hash")
        doc2 = _make_doc(doc_id="doc_2", content_hash="same_hash")

        with caplog.at_level(logging.INFO):
            index.build([doc1, doc2])

        assert "removed 1 duplicate" in caplog.text


# =============================================================================
# Persistence Tests
# =============================================================================


class TestBM25Persistence:
    """Tests for save/load (pickle round-trip)."""

    def test_save_and_load(self, index: BM25Index, tmp_path: Path) -> None:
        """Index survives save/load cycle."""
        docs = [
            _make_doc(doc_id="doc_1", text="persistent content alpha beta"),
            _make_doc(doc_id="doc_2", text="persistent content gamma delta"),
        ]
        index.build(docs)
        index.save()

        # Create a new index and load
        new_index = BM25Index(index_path=tmp_path / "bm25_index.pkl")
        loaded_count = new_index.load()

        assert loaded_count == 2
        assert new_index.document_count == 2

        # Search should still work
        results = new_index.search("alpha beta")
        assert len(results) == 1
        assert results[0].doc_id == "doc_1"

    def test_save_creates_directory(self, tmp_path: Path) -> None:
        """Save creates parent directories if needed."""
        deep_path = tmp_path / "deep" / "nested" / "bm25.pkl"
        index = BM25Index(index_path=deep_path)
        index.build([_make_doc()])
        index.save()

        assert deep_path.exists()

    def test_load_nonexistent_raises(self, index: BM25Index) -> None:
        """Loading a non-existent file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            index.load()

    def test_save_without_path_raises(self) -> None:
        """Saving without a path raises ValueError."""
        index = BM25Index(index_path=None)
        index.build([_make_doc()])

        with pytest.raises(ValueError, match="No index path"):
            index.save()
