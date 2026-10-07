"""Tests for settings-driven repository config and BM25 rebuild (E2/E3)."""

import os
from datetime import datetime
from pathlib import Path

from app.models.enriched_article import EnrichedArticle
from app.models.metadata import ExtractionResult
from app.models.normalized_article import NormalizedArticle
from app.services.knowledge.object_assembler import KnowledgeObjectAssembler
from app.services.knowledge.object_builder import ObjectBuilder
from app.services.knowledge.object_validator import KnowledgeObjectValidator
from app.services.repository.bootstrap import build_repository_config
from app.services.repository.config import RepositoryConfig
from app.services.repository.initializer import RepositoryInitializer
from app.storage.knowledge.sqlite_store import SQLiteKnowledgeStore

REQUIRED_ENV = {
    "GROQ_API_KEY": "test-groq-key",
    "COHERE_API_KEY": "test-cohere-key",
    "QDRANT_URL": "https://qdrant.example.com",
    "QDRANT_API_KEY": "test-qdrant-key",
    "ZALO_APP_ID": "test-zalo-app-id",
    "ZALO_APP_SECRET": "test-zalo-app-secret",
    "ZALO_ACCESS_TOKEN": "test-zalo-access-token",
    "ZALO_WEBHOOK_SECRET": "test-zalo-webhook-secret",
}


def _make_settings(monkeypatch, **overrides):
    for key, value in REQUIRED_ENV.items():
        monkeypatch.setenv(key, value)
    for key in (
        "SQLITE_PATH",
        "BM25_INDEX_PATH",
        "EMBEDDING_PROVIDER",
        "OLLAMA_BASE_URL",
    ):
        if key in overrides:
            monkeypatch.setenv(key, overrides[key])
        else:
            monkeypatch.delenv(key, raising=False)
    from app.config.settings import Settings

    return Settings(_env_file=None)


class TestBuildRepositoryConfig:
    def test_defaults_point_at_source_tree_paths(self, monkeypatch):
        """Backward compatible: no env → same paths the code hard-coded before."""
        settings = _make_settings(monkeypatch)
        config = build_repository_config(settings)

        assert config.sqlite_path == Path("app/storage/knowledge/knowledge.db")
        assert config.bm25_index_path == Path("app/storage/search/bm25_index.pkl")
        assert config.embedding_provider_type == "ollama"
        assert config.ollama_base_url == "http://localhost:11434"

    def test_paths_and_embedding_are_settings_driven(self, monkeypatch, tmp_path):
        """E2/E3: deploy sets paths + embedding provider purely via env."""
        settings = _make_settings(
            monkeypatch,
            SQLITE_PATH=str(tmp_path / "data" / "knowledge.db"),
            BM25_INDEX_PATH=str(tmp_path / "search" / "bm25.pkl"),
            EMBEDDING_PROVIDER="cohere",
            OLLAMA_BASE_URL="http://embed.internal:11434",
        )
        config = build_repository_config(settings)

        assert config.sqlite_path == tmp_path / "data" / "knowledge.db"
        assert config.bm25_index_path == tmp_path / "search" / "bm25.pkl"
        assert config.embedding_provider_type == "cohere"
        assert config.ollama_base_url == "http://embed.internal:11434"
        assert config.cohere_api_key == "test-cohere-key"


class TestBM25Rebuild:
    """E2: deleting the index file must never lose search capability."""

    @staticmethod
    def _seed_sqlite(db_path: Path, count: int) -> SQLiteKnowledgeStore:
        store = SQLiteKnowledgeStore(db_path=db_path)
        assembler = KnowledgeObjectAssembler(
            builder=ObjectBuilder(),
            validator=KnowledgeObjectValidator(),
            store=store,
        )
        enriched = []
        for i in range(count):
            norm = NormalizedArticle(
                article_id=f"norm_{i}",
                title=f"Rebuild Article {i}",
                content=f"Content body number {i} for the rebuild test.",
                url=f"https://example.com/rebuild/{i}",
                source_name="test",
                source_type="rss",
                author=None,
                published_date=None,
                fetched_at=datetime(2025, 1, 1),
                raw_content_hash=f"raw_{i}",
            )
            enriched.append(
                EnrichedArticle(
                    article=norm,
                    extraction=ExtractionResult(
                        summary="s", topics=["t"], entities=["e"], relevance_score=0.5
                    ),
                    extraction_status="success",
                )
            )
        assembler.assemble(enriched)
        return store

    def test_missing_index_rebuilds_from_sqlite(self, tmp_path: Path):
        """Plan test: delete pkl + SQLite has data → rebuild, doc count matches."""
        db_path = tmp_path / "knowledge.db"
        pkl_path = tmp_path / "search" / "bm25.pkl"
        store = self._seed_sqlite(db_path, count=3)
        sqlite_count = store.count()
        store.close()

        assert not pkl_path.exists()

        config = RepositoryConfig(
            sqlite_path=db_path,
            qdrant_url="http://localhost:6333",
            bm25_index_path=pkl_path,
            embedding_provider_type="ollama",
            auto_create_collections=False,
        )
        initializer = RepositoryInitializer(config)
        # Simulate initialize() ordering: SQLite exists before BM25 init
        initializer._sqlite_store = SQLiteKnowledgeStore(db_path=db_path)
        index = initializer._init_bm25()

        assert index.document_count == sqlite_count == 3
        assert pkl_path.exists()  # rebuilt index was persisted

        # A fresh initializer loads the persisted rebuild instead of rebuilding
        initializer_2 = RepositoryInitializer(config)
        initializer_2._sqlite_store = SQLiteKnowledgeStore(db_path=db_path)
        index_2 = initializer_2._init_bm25()
        assert index_2.document_count == 3

    def test_missing_index_with_empty_sqlite_starts_empty(self, tmp_path: Path):
        db_path = tmp_path / "empty.db"
        pkl_path = tmp_path / "search" / "bm25.pkl"
        SQLiteKnowledgeStore(db_path=db_path).close()

        config = RepositoryConfig(
            sqlite_path=db_path,
            qdrant_url="http://localhost:6333",
            bm25_index_path=pkl_path,
            embedding_provider_type="ollama",
            auto_create_collections=False,
        )
        initializer = RepositoryInitializer(config)
        initializer._sqlite_store = SQLiteKnowledgeStore(db_path=db_path)
        index = initializer._init_bm25()

        assert index.document_count == 0
        assert not pkl_path.exists()  # nothing to persist


class TestSettingsDefaults:
    def test_storage_and_embedding_settings_exist(self, monkeypatch):
        settings = _make_settings(monkeypatch)

        assert os.environ.get("SQLITE_PATH") is None  # env untouched
        assert settings.sqlite_path == Path("app/storage/knowledge/knowledge.db")
        assert settings.bm25_index_path == Path("app/storage/search/bm25_index.pkl")
        assert settings.embedding_provider == "ollama"
        assert settings.ollama_base_url == "http://localhost:11434"
