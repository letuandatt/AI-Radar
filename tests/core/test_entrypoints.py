"""Tests for the D2 batch entrypoints and E1 bootstrap boundaries."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import yaml

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


def _clean_settings_cache():
    from app.config.settings import get_settings

    get_settings.cache_clear()


def _setup_env(monkeypatch):
    for key, value in REQUIRED_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("SQLITE_PATH", raising=False)
    monkeypatch.delenv("BM25_INDEX_PATH", raising=False)
    _clean_settings_cache()


class TestUpdateKnowledgeEntrypoint:
    def test_dry_run_bootstraps_nothing(self, monkeypatch, capsys):
        """Dry run: lists components, exits 0, NEVER touches the network (E1)."""
        _setup_env(monkeypatch)

        import scripts.update_knowledge as entrypoint

        with (
            patch(
                "app.services.repository.bootstrap.initialize_knowledge_repository",
                side_effect=AssertionError("dry run must not initialize"),
            ),
            patch(
                "app.services.repository.bootstrap.create_llm_chain",
                side_effect=AssertionError("dry run must not create llm chain"),
            ),
        ):
            exit_code = entrypoint.main(["--dry-run"])

        assert exit_code == 0
        output = capsys.readouterr().out
        assert "DRY RUN OK" in output
        assert "repository" in output
        assert "llm_chain" in output

    def test_real_run_bootstraps_batch_dependencies_only(self, monkeypatch):
        """E1: batch runtime inits repository+llm_chain+pipelines, NOT retrieval."""
        _setup_env(monkeypatch)

        import scripts.update_knowledge as entrypoint

        bootstrapped: list[str] = []

        def _fake_init(settings):
            bootstrapped.append("repository")
            initializer = MagicMock()
            initializer.sqlite_store = MagicMock()
            return initializer

        def _fake_analysis(initializer, chain):
            bootstrapped.append("analysis")
            analyzer = MagicMock()
            analyzer.analyze_batch = AsyncMock(return_value=[])
            return analyzer

        with (
            patch(
                "app.services.repository.bootstrap.initialize_knowledge_repository",
                side_effect=_fake_init,
            ),
            patch(
                "app.services.repository.bootstrap.create_llm_chain",
                side_effect=lambda s: bootstrapped.append("llm_chain"),
            ),
            patch(
                "app.pipelines.knowledge_update.build_processing_pipeline",
                side_effect=lambda i, s, c: bootstrapped.append("processing"),
            ),
            patch("app.fetchers.registry.initialize_source_registry"),
            patch("app.fetchers.registry.initialize_github_registry"),
            patch("app.fetchers.registry.initialize_hf_registry"),
            patch("app.fetchers.registry.get_source_registry", return_value=MagicMock()),
            patch("app.fetchers.registry.get_github_registry", return_value=MagicMock()),
            patch("app.fetchers.registry.get_hf_registry", return_value=MagicMock()),
            patch("app.pipelines.acquisition.DefaultAcquisitionPipeline") as mock_acq,
            patch(
                "app.services.repository.bootstrap.create_analysis_service",
                side_effect=_fake_analysis,
            ),
        ):
            mock_pipeline = mock_acq.return_value
            mock_pipeline.run.return_value.total_articles = 0

            exit_code = entrypoint.main([])

        assert exit_code == 0
        # E1: exactly the batch dependencies — no retrieval, no scheduler, no web
        assert bootstrapped == ["repository", "llm_chain", "processing", "analysis"]


class TestSendDigestEntrypoint:
    def test_dry_run_bootstraps_nothing(self, monkeypatch, capsys):
        _setup_env(monkeypatch)

        import scripts.send_digest as entrypoint

        with patch(
            "app.services.repository.bootstrap.initialize_knowledge_repository",
            side_effect=AssertionError("dry run must not initialize"),
        ):
            exit_code = entrypoint.main(["--dry-run"])

        assert exit_code == 0
        output = capsys.readouterr().out
        assert "DRY RUN OK" in output
        assert "digest pipeline" in output
        assert "digest_enabled" in output

    def test_disabled_digest_is_noop_without_bootstrap(self, monkeypatch):
        """digest_enabled=False (default): registered job runs as a no-op."""
        _setup_env(monkeypatch)
        monkeypatch.delenv("DIGEST_ENABLED", raising=False)
        _clean_settings_cache()

        import scripts.send_digest as entrypoint

        with patch(
            "app.services.repository.bootstrap.initialize_knowledge_repository",
            side_effect=AssertionError("disabled digest must not bootstrap"),
        ):
            exit_code = entrypoint.main([])

        assert exit_code == 0
        _clean_settings_cache()

    def test_enabled_digest_runs_pipeline(self, monkeypatch):
        _setup_env(monkeypatch)
        monkeypatch.setenv("DIGEST_ENABLED", "true")
        _clean_settings_cache()

        import scripts.send_digest as entrypoint

        bootstrapped: list[str] = []
        mock_result = MagicMock()
        mock_result.sent = True
        mock_result.items = [MagicMock(), MagicMock()]
        mock_pipeline = MagicMock()
        mock_pipeline.run.return_value = mock_result

        with (
            patch(
                "app.services.repository.bootstrap.initialize_knowledge_repository",
                side_effect=lambda s: (
                    bootstrapped.append("repository") or MagicMock(sqlite_store=MagicMock())
                ),
            ),
            patch(
                "app.services.repository.bootstrap.create_llm_chain",
                side_effect=lambda s: bootstrapped.append("llm_chain"),
            ),
            patch(
                "app.pipelines.daily_digest.DailyDigestPipeline",
                side_effect=lambda **kwargs: bootstrapped.append("digest") or mock_pipeline,
            ),
        ):
            exit_code = entrypoint.main([])

        assert exit_code == 0
        # E1: digest runtime = repository + llm_chain + pipeline (no acquisition)
        assert bootstrapped == ["repository", "llm_chain", "digest"]
        _clean_settings_cache()

    def test_failed_delivery_exits_nonzero(self, monkeypatch):
        _setup_env(monkeypatch)
        monkeypatch.setenv("DIGEST_ENABLED", "true")
        _clean_settings_cache()

        import scripts.send_digest as entrypoint

        mock_result = MagicMock()
        mock_result.sent = False
        mock_result.error = "Zalo API down"
        mock_result.items = [MagicMock()]
        mock_pipeline = MagicMock()
        mock_pipeline.run.return_value = mock_result

        with (
            patch(
                "app.services.repository.bootstrap.initialize_knowledge_repository",
                return_value=MagicMock(sqlite_store=MagicMock()),
            ),
            patch("app.services.repository.bootstrap.create_llm_chain", return_value=MagicMock()),
            patch(
                "app.pipelines.daily_digest.DailyDigestPipeline",
                return_value=mock_pipeline,
            ),
        ):
            exit_code = entrypoint.main([])

        assert exit_code == 1  # delivery failure surfaced to the schedule
        _clean_settings_cache()


class TestGitHubWorkflows:
    """D2: workflows must run the entrypoints with secrets + dry-run first."""

    @staticmethod
    def _load_workflow(path: Path) -> dict:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        # YAML 1.1 parses a bare `on:` key as boolean True — normalize it.
        if "on" not in data and True in data:
            data["on"] = data.pop(True)
        return data

    def test_workflows_are_valid_and_wired(self):
        base = Path(".github/workflows")
        for name, script, group in [
            ("knowledge_update.yml", "scripts/update_knowledge.py", "knowledge-update"),
            ("daily_digest.yml", "scripts/send_digest.py", "daily-digest"),
        ]:
            data = self._load_workflow(base / name)

            assert "schedule" in data["on"], f"{name}: missing schedule trigger"
            assert "workflow_dispatch" in data["on"], f"{name}: missing manual trigger"
            cron = data["on"]["schedule"][0]["cron"]
            assert cron.split()[0] in {"30", "0"}  # minute field is explicit

            job = data["jobs"][list(data["jobs"])[0]]
            run_steps = [s.get("run", "") for s in job["steps"] if isinstance(s, dict)]
            assert any("--dry-run" in r for r in run_steps), f"{name}: dry-run first"
            assert any(script in r and "--dry-run" not in r for r in run_steps), (
                f"{name}: real run of {script}"
            )
            assert "GROQ_API_KEY" in job["env"]
            assert "secrets.GROQ_API_KEY" in str(job["env"]["GROQ_API_KEY"])
            assert "checkout" in str(job["steps"][0])
            assert data["concurrency"]["group"] == group

    def test_cron_schedule_order_is_update_then_digest(self):
        update = self._load_workflow(Path(".github/workflows/knowledge_update.yml"))
        digest = self._load_workflow(Path(".github/workflows/daily_digest.yml"))
        assert update["on"]["schedule"][0]["cron"] < digest["on"]["schedule"][0]["cron"], (
            "digest must run AFTER knowledge update"
        )
