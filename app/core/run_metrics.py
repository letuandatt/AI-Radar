"""Run-level observability: one JSON line per pipeline run (P1.9).

Each batch run (knowledge update, digest) records a single metrics line:
run_id, kind, timing, and the run's outcome fields (articles fetched/dedup/
kept/created/failed, llm calls/tokens/cost deltas, digest delivery status).
Metrics live in ``settings.run_metrics_path`` (JSONL — one append per run).
"""

import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.logger import get_logger

logger = get_logger(__name__)


@dataclass
class RunMetrics:
    """Metrics for ONE run. Create with :meth:`start`, finish with :meth:`finish`."""

    run_id: str
    kind: str
    started_at: str
    started_perf: float = field(default_factory=time.perf_counter, repr=False)
    finished_at: str | None = None
    duration_seconds: float = 0.0
    metrics: dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def start(kind: str) -> "RunMetrics":
        """Begin a run of ``kind`` (e.g. "knowledge_update", "digest")."""
        return RunMetrics(
            run_id=uuid.uuid4().hex[:12],
            kind=kind,
            started_at=datetime.now(timezone.utc).isoformat(),
        )

    def set(self, **values: Any) -> None:
        """Attach outcome fields to the run."""
        self.metrics.update(values)

    def finish(self) -> None:
        """Stamp the end time and duration."""
        self.finished_at = datetime.now(timezone.utc).isoformat()
        self.duration_seconds = round(time.perf_counter() - self.started_perf, 3)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "kind": self.kind,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_seconds": self.duration_seconds,
            "metrics": self.metrics,
        }

    def save_jsonl(self, path: Path) -> Path:
        """Append this run as one JSON line (creates the file if missing)."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(self.to_dict(), ensure_ascii=False) + "\n")
        logger.info("Run metrics saved: %s (%s, %.3fs)", path, self.kind, self.duration_seconds)
        return path
