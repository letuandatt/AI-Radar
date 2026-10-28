"""Batch startup must expose INFO logs before loading settings/bootstrap."""

import logging
from types import SimpleNamespace

from scripts.update_knowledge import main


def test_logging_is_initialized_before_settings(monkeypatch, caplog):
    from app.config import settings as config

    root = logging.getLogger()
    previous_level = root.level

    def settings():
        logging.getLogger("batch_startup_probe").info("startup is visible")
        return SimpleNamespace(sqlite_path="unused.db", llm_primary_provider="ollama")

    monkeypatch.setattr(config, "get_settings", settings)
    try:
        root.setLevel(logging.WARNING)
        assert main(["--analysis-only", "--dry-run"]) == 0
        assert "startup is visible" in caplog.text
    finally:
        root.setLevel(previous_level)
