"""Tests for LLMLogger."""

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.integrations.llm.logger import LLMLogger


class TestLLMLogger:
    def test_log_success(self, tmp_path: Path):
        db_path = tmp_path / "test.db"
        logger = LLMLogger(db_path)

        logger.log(
            provider="ollama",
            model="qwen3:4b",
            prompt="Hello",
            response="Hi there",
            tokens_in=10,
            tokens_out=20,
            latency_ms=100.0,
            cost_usd=0.0,
            status="success",
        )

        conn = sqlite3.connect(db_path)
        cursor = conn.execute("SELECT COUNT(*) FROM llm_logs")
        assert cursor.fetchone()[0] == 1
        conn.close()

    def test_log_error(self, tmp_path: Path):
        db_path = tmp_path / "test.db"
        logger = LLMLogger(db_path)

        logger.log(
            provider="groq",
            model="llama-3.1-70b",
            prompt="Hello",
            response=None,
            tokens_in=0,
            tokens_out=0,
            latency_ms=0.0,
            cost_usd=0.0,
            status="error",
            error_type="ConnectionError",
            error_message="Timeout",
        )

        conn = sqlite3.connect(db_path)
        cursor = conn.execute("SELECT status, error_type FROM llm_logs")
        row = cursor.fetchone()
        assert row[0] == "error"
        assert row[1] == "ConnectionError"
        conn.close()

    def test_get_stats(self, tmp_path: Path):
        db_path = tmp_path / "test.db"
        logger = LLMLogger(db_path)

        logger.log("ollama", "qwen3:4b", "P1", "R1", 10, 20, 100.0, 0.01, "success")
        logger.log("ollama", "qwen3:4b", "P2", "R2", 15, 25, 150.0, 0.02, "success")
        logger.log("ollama", "qwen3:4b", "P3", None, 0, 0, 0.0, 0.0, "error", "Error", "Fail")

        stats = logger.get_stats(days=7)
        assert stats["total_calls"] == 3
        assert stats["total_cost"] == 0.03
        assert stats["success_rate"] == pytest.approx(66.67, rel=1e-2)

    def test_log_persists_request_type_and_estimated_flag(self, tmp_path: Path):
        db_path = tmp_path / "test.db"
        logger = LLMLogger(db_path)

        logger.log(
            provider="groq",
            model="qwen/qwen3.8-27b",
            prompt="Hello",
            response="{}",
            tokens_in=100,
            tokens_out=50,
            latency_ms=100.0,
            cost_usd=0.001,
            status="success",
            request_type="structured_chat",
            tokens_estimated=True,
        )

        conn = sqlite3.connect(db_path)
        cursor = conn.execute("SELECT request_type, tokens_estimated FROM llm_logs")
        row = cursor.fetchone()
        conn.close()
        assert row[0] == "structured_chat"
        assert row[1] == 1

    def test_init_migrates_legacy_table_without_new_columns(self, tmp_path: Path):
        db_path = tmp_path / "legacy.db"
        conn = sqlite3.connect(db_path)
        conn.execute(
            """
            CREATE TABLE llm_logs (
                log_id TEXT PRIMARY KEY,
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                prompt TEXT,
                response TEXT,
                tokens_in INTEGER,
                tokens_out INTEGER,
                latency_ms REAL,
                cost_usd REAL,
                status TEXT NOT NULL,
                error_type TEXT,
                error_message TEXT,
                prompt_name TEXT,
                prompt_version TEXT,
                created_at TIMESTAMP NOT NULL
            )
            """
        )
        conn.commit()
        conn.close()

        LLMLogger(db_path)

        conn = sqlite3.connect(db_path)
        columns = {row[1] for row in conn.execute("PRAGMA table_info(llm_logs)")}
        conn.close()
        assert "request_type" in columns
        assert "tokens_estimated" in columns


@pytest.mark.parametrize("retention_days", [30, 7])
def test_cleanup_respects_retention_boundary(tmp_path, monkeypatch, retention_days):
    now = datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc)

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return now

    monkeypatch.setattr("app.integrations.llm.logger.datetime", FrozenDateTime)

    db_path = tmp_path / "retention.db"
    if retention_days == 30:
        logger = LLMLogger(db_path)
    else:
        logger = LLMLogger(db_path, retention_days=retention_days)

    cutoff = now - timedelta(days=retention_days)

    with sqlite3.connect(db_path) as conn:
        conn.executemany(
            """
            INSERT INTO llm_logs (
                log_id, provider, model, status, created_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            [
                (
                    "old",
                    "ollama",
                    "test",
                    "success",
                    (cutoff - timedelta(seconds=1)).isoformat(),
                ),
                ("boundary", "ollama", "test", "success", cutoff.isoformat()),
                ("recent", "ollama", "test", "success", now.isoformat()),
            ],
        )

    assert logger.cleanup_old_logs() == 1

    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT log_id FROM llm_logs ORDER BY log_id").fetchall() == [
            ("boundary",),
            ("recent",),
        ]

    assert logger.cleanup_old_logs() == 0
