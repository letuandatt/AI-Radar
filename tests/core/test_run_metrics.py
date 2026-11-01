"""Tests for run-level metrics (P1.9)."""

import json
from pathlib import Path

from app.core.run_metrics import RunMetrics


class TestRunMetrics:
    def test_start_finish_lifecycle(self):
        run = RunMetrics.start("knowledge_update")
        run.set(articles_fetched=42, objects_created=7)
        run.finish()

        data = run.to_dict()
        assert data["kind"] == "knowledge_update"
        assert data["run_id"]
        assert data["finished_at"] >= data["started_at"]
        assert data["duration_seconds"] >= 0
        assert data["metrics"]["articles_fetched"] == 42

    def test_save_jsonl_appends_one_line_per_run(self, tmp_path: Path):
        path = tmp_path / "metrics" / "runs.jsonl"

        first = RunMetrics.start("digest")
        first.set(digest_sent=True)
        first.finish()
        first.save_jsonl(path)

        second = RunMetrics.start("digest")
        second.finish()
        second.save_jsonl(path)

        lines = path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 2
        parsed = [json.loads(line) for line in lines]
        assert parsed[0]["metrics"]["digest_sent"] is True
        assert parsed[0]["run_id"] != parsed[1]["run_id"]
