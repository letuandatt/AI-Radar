"""LLM Observability Logger."""

import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.core.logger import get_logger

logger = get_logger(__name__)


class LLMLogger:
    """
    Logs LLM calls to SQLite for observability.

    Args:
        db_path: Path to SQLite database.
        retention_days: Days to retain logs (default 30).
    """

    def __init__(self, db_path: Path, retention_days: int = 30) -> None:
        self.db_path = db_path
        self.retention_days = retention_days
        self._init_table()

    def _init_table(self) -> None:
        """Create llm_logs table if not exists, migrating older schemas."""
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("""
                         CREATE TABLE IF NOT EXISTS llm_logs
                         (
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
                             request_type TEXT,
                             tokens_estimated INTEGER,
                             created_at TIMESTAMP NOT NULL
                         )
                         """)
            conn.execute("""
                         CREATE INDEX IF NOT EXISTS idx_llm_logs_created_at
                             ON llm_logs(created_at)
                         """)
            self._migrate_columns(conn)
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _migrate_columns(conn: sqlite3.Connection) -> None:
        """Add columns introduced after the initial schema (no-op when present)."""
        existing = {row[1] for row in conn.execute("PRAGMA table_info(llm_logs)")}
        migrations = {
            "request_type": "TEXT",
            "tokens_estimated": "INTEGER",
        }
        for column, declaration in migrations.items():
            if column not in existing:
                conn.execute(f"ALTER TABLE llm_logs ADD COLUMN {column} {declaration}")

    def log(
        self,
        provider: str,
        model: str,
        prompt: str,
        response: str | None,
        tokens_in: int,
        tokens_out: int,
        latency_ms: float,
        cost_usd: float,
        status: str,
        error_type: str | None = None,
        error_message: str | None = None,
        prompt_name: str | None = None,
        prompt_version: str | None = None,
        request_type: str = "chat",
        tokens_estimated: bool = False,
    ) -> None:
        """
        Log an LLM call.

        Args:
            provider: Provider name.
            model: Model name.
            prompt: Input prompt.
            response: Output response (None if error).
            tokens_in: Input tokens.
            tokens_out: Output tokens.
            latency_ms: Latency in milliseconds.
            cost_usd: Cost in USD.
            status: "success" or "error".
            error_type: Exception class name (if error).
            error_message: Error message (if error).
            prompt_name: Prompt template name (optional).
            prompt_version: Prompt version (optional).
            request_type: "chat" or "structured_chat" (for cost-per-workload queries).
            tokens_estimated: True when token counts are length-based estimates,
                not metered usage.
        """
        log_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc).isoformat()

        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                """
                INSERT INTO llm_logs (log_id, provider, model, prompt, response,
                                      tokens_in, tokens_out, latency_ms, cost_usd,
                                      status, error_type, error_message,
                                      prompt_name, prompt_version,
                                      request_type, tokens_estimated, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    log_id,
                    provider,
                    model,
                    prompt,
                    response,
                    tokens_in,
                    tokens_out,
                    latency_ms,
                    cost_usd,
                    status,
                    error_type,
                    error_message,
                    prompt_name,
                    prompt_version,
                    request_type,
                    int(tokens_estimated),
                    created_at,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def cleanup_old_logs(self) -> int:
        """
        Delete logs older than retention_days.

        Returns:
            Number of deleted rows.
        """
        cutoff = (datetime.now(timezone.utc) - timedelta(days=self.retention_days)).isoformat()

        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.execute(
                "DELETE FROM llm_logs WHERE created_at < ?",
                (cutoff,),
            )
            conn.commit()
            deleted = cursor.rowcount
            if deleted > 0:
                logger.info("LLMLogger: Cleaned up %d old logs", deleted)
            return deleted
        finally:
            conn.close()

    def get_stats(self, days: int = 7) -> dict:
        """
        Get aggregated stats for the last N days.

        Returns:
            Dict with total_calls, total_cost, avg_latency_ms, success_rate.
        """
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.execute(
                """
                SELECT COUNT(*)                                            as total_calls,
                       SUM(cost_usd)                                       as total_cost,
                       AVG(latency_ms)                                     as avg_latency_ms,
                       SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as success_count
                FROM llm_logs
                WHERE created_at >= ?
                """,
                (cutoff,),
            )
            row = cursor.fetchone()
            if row:
                total_calls, total_cost, avg_latency_ms, success_count = row
                success_rate = (success_count / total_calls * 100) if total_calls > 0 else 0.0
                return {
                    "total_calls": total_calls,
                    "total_cost": total_cost or 0.0,
                    "avg_latency_ms": avg_latency_ms or 0.0,
                    "success_rate": success_rate,
                }
            return {
                "total_calls": 0,
                "total_cost": 0.0,
                "avg_latency_ms": 0.0,
                "success_rate": 0.0,
            }
        finally:
            conn.close()
