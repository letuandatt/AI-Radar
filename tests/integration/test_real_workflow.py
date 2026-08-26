"""Real Integration Test - Sprint 08 Workflow.

This test executes the FULL workflow of Sprint 08 against REAL external sources
(NO MOCKS). It validates that the entire source management pipeline works
end-to-end in a production-like environment.

**Workflow Tested:**
1. Pre-flight Validation: Check real RSS, GitHub, HuggingFace sources
2. Source Configuration: Register sources via SourceConfigService
3. Status Management: Mark inactive → mark active (with re-validation)
4. Persistence: Verify data/source_status.json is created correctly

**Requirements:**
- Internet connection
- Valid API access (no tokens required for these public sources)

**Sources Used:**
- RSS: TechCrunch (https://techcrunch.com/feed/)
- GitHub: tiangolo/fastapi (public repo)
- HuggingFace: google-bert/bert-base-uncased (public model)
"""

import json
import shutil
from pathlib import Path

import pytest

from app.models.source import GitHubRepository, HFSource, HFSourceType, RSSSource
from app.services.source_config_service import SourceConfigService
from app.services.source_status_service import SourceStatusService
from app.services.source_validator import (
    GitHubValidator,
    HuggingFaceValidator,
    RSSValidator,
)
from app.storage.source_status import SourceStatusStorage

# ==============================================================================
# Test Data (Real Public Sources)
# ==============================================================================

REAL_RSS_SOURCE = {
    "name": "techcrunch_real",
    "url": "https://techcrunch.com/feed/",
}

REAL_GITHUB_SOURCE = {
    "name": "fastapi_real",
    "owner": "tiangolo",
    "repo": "fastapi",
}

REAL_HF_SOURCE = {
    "name": "bert_real",
    "resource_id": "google-bert/bert-base-uncased",
    "source_type": "model",
}

DATA_DIR = Path("data")
STATUS_FILE = DATA_DIR / "source_status.json"


# ==============================================================================
# Fixtures
# ==============================================================================

@pytest.fixture(autouse=True)
def cleanup_data_dir():
    """Clean up data/ directory before and after each test."""
    # Setup: ensure clean state
    if DATA_DIR.exists():
        # Keep other files (like history.json), only remove source_status.json
        if STATUS_FILE.exists():
            STATUS_FILE.unlink()

    yield

    # Teardown: clean up created files
    if STATUS_FILE.exists():
        STATUS_FILE.unlink()


@pytest.fixture
def real_registries():
    """Create real (in-memory) registries for integration testing."""
    from app.config.settings import Settings
    from app.fetchers.registry import (
        ConfigBasedGitHubRegistry,
        ConfigBasedHFRegistry,
        ConfigBasedSourceRegistry,
    )

    # Tạo một object Settings giả lập hợp lệ để thỏa mãn constructor của Registry
    dummy_settings = Settings(
        groq_api_key="test_key",
        cohere_api_key="test_key",
        qdrant_url="http://localhost:6333",
        qdrant_api_key="test_key",
        zalo_app_id="test",
        zalo_app_secret="test",
        zalo_access_token="test",
        zalo_webhook_secret="test",
        rss_sources=[],
        github_repositories=[],
        hf_sources=[],
    )

    rss_registry = ConfigBasedSourceRegistry(dummy_settings)
    github_registry = ConfigBasedGitHubRegistry(dummy_settings)
    hf_registry = ConfigBasedHFRegistry(dummy_settings)

    return rss_registry, github_registry, hf_registry


@pytest.fixture
def config_service(real_registries):
    """Provide a real SourceConfigService instance."""
    rss_reg, gh_reg, hf_reg = real_registries
    return SourceConfigService(rss_reg, gh_reg, hf_reg)


@pytest.fixture
def status_service(real_registries):
    """Provide a real SourceStatusService instance with real storage."""
    rss_reg, gh_reg, hf_reg = real_registries
    storage = SourceStatusStorage(file_path=STATUS_FILE)
    return SourceStatusService(storage, rss_reg, gh_reg, hf_reg)


# ==============================================================================
# Stage 1: Pre-flight Validation (T108 Real)
# ==============================================================================

@pytest.mark.integration
@pytest.mark.slow
class TestStage1_Validation:
    """Stage 1: Validate real sources using SourceValidator (T108)."""

    def test_validate_real_rss_source(self):
        """Verify that TechCrunch RSS feed is accessible and valid."""
        validator = RSSValidator(timeout=15.0)
        source = RSSSource(name=REAL_RSS_SOURCE["name"], url=REAL_RSS_SOURCE["url"])

        result = validator.validate(source)

        assert result.is_valid is True, f"RSS validation failed: {result.error_message}"
        assert result.details.get("url") == REAL_RSS_SOURCE["url"]
        print(f"\n✅ RSS Validated: {source.url}")

    def test_validate_real_github_source(self):
        """Verify that tiangolo/fastapi GitHub repo is accessible."""
        validator = GitHubValidator(timeout=15.0)
        source = GitHubRepository(
            name=REAL_GITHUB_SOURCE["name"],
            owner=REAL_GITHUB_SOURCE["owner"],
            repo=REAL_GITHUB_SOURCE["repo"],
        )

        result = validator.validate(source)

        assert result.is_valid is True, f"GitHub validation failed: {result.error_message}"
        print(f"\n✅ GitHub Validated: {source.owner}/{source.repo}")

    def test_validate_real_huggingface_source(self):
        """Verify that bert-base-uncased model is accessible on HuggingFace."""
        validator = HuggingFaceValidator(timeout=15.0)
        source = HFSource(
            name=REAL_HF_SOURCE["name"],
            resource_id=REAL_HF_SOURCE["resource_id"],
            source_type=HFSourceType.MODEL,
        )

        result = validator.validate(source)

        assert result.is_valid is True, f"HuggingFace validation failed: {result.error_message}"
        print(f"\n✅ HuggingFace Validated: {source.resource_id}")


# ==============================================================================
# Stage 2: Source Configuration (T104 Real)
# ==============================================================================

@pytest.mark.integration
@pytest.mark.slow
class TestStage2_Configuration:
    """Stage 2: Register real sources via SourceConfigService (T104)."""

    def test_update_real_rss_source(self, config_service, real_registries):
        """Register TechCrunch RSS and verify it appears in registry."""
        rss_reg, _, _ = real_registries

        result = config_service.update_source(
            source_type="rss",
            name=REAL_RSS_SOURCE["name"],
            config={"url": REAL_RSS_SOURCE["url"]},
        )

        assert result.is_valid is True, f"Config update failed: {result.error_message}"

        # Verify it's in the registry
        registered = rss_reg.get_by_name(REAL_RSS_SOURCE["name"])
        assert registered.url == REAL_RSS_SOURCE["url"]
        print(f"\n✅ RSS Registered: {registered.name}")

    def test_update_real_github_source(self, config_service, real_registries):
        """Register FastAPI GitHub repo and verify."""
        _, gh_reg, _ = real_registries

        result = config_service.update_source(
            source_type="github",
            name=REAL_GITHUB_SOURCE["name"],
            config={
                "owner": REAL_GITHUB_SOURCE["owner"],
                "repo": REAL_GITHUB_SOURCE["repo"],
            },
        )

        assert result.is_valid is True, f"Config update failed: {result.error_message}"

        registered = gh_reg.get_by_name(REAL_GITHUB_SOURCE["name"])
        assert registered.owner == "tiangolo"
        assert registered.repo == "fastapi"
        print(f"\n✅ GitHub Registered: {registered.name}")

    def test_update_real_huggingface_source(self, config_service, real_registries):
        """Register BERT HuggingFace model and verify."""
        _, _, hf_reg = real_registries

        result = config_service.update_source(
            source_type="huggingface",
            name=REAL_HF_SOURCE["name"],
            config={
                "resource_id": REAL_HF_SOURCE["resource_id"],
                "source_type": "model",
            },
        )

        assert result.is_valid is True, f"Config update failed: {result.error_message}"

        registered = hf_reg.get_by_name(REAL_HF_SOURCE["name"])
        assert registered.resource_id == REAL_HF_SOURCE["resource_id"]
        print(f"\n✅ HuggingFace Registered: {registered.name}")

    def test_get_source_schema(self, config_service):
        """Verify that JSON schema is correctly exposed (INFRA-002 prep)."""
        schema = config_service.get_source_schema("rss")

        assert schema is not None
        assert "properties" in schema
        assert "url" in schema["properties"]
        print(f"\n✅ JSON Schema Exposed for RSS: {list(schema['properties'].keys())}")


# ==============================================================================
# Stage 3: Status Management (T106 Real)
# ==============================================================================

@pytest.mark.integration
@pytest.mark.slow
class TestStage3_StatusManagement:
    """Stage 3: Manage source status via SourceStatusService (T106)."""

    def test_mark_inactive_real_source(self, status_service):
        """Mark a source as inactive and verify persistence."""
        status_service.mark_inactive(
            source_name="techcrunch_real",
            source_type="rss",
            error_message="Simulated network error for testing",
        )

        # Verify file was created
        assert STATUS_FILE.exists(), "source_status.json should be created"

        # Verify content
        status = status_service.get_status("techcrunch_real")
        assert status is not None
        assert status.is_active is False
        assert status.error_message == "Simulated network error for testing"
        assert status.last_checked is not None

        print(f"\n✅ Marked Inactive: {status.source_name} - {status.error_message}")

    def test_mark_active_with_revalidation(self, status_service, real_registries):
        """Mark source as active WITH re-validation (T106 hook).

        This test verifies the critical hook: when re-activating a source,
        the service MUST call SourceValidator to confirm it's still valid.
        """
        rss_reg, _, _ = real_registries

        # First, register the source in registry (required for re-validation)
        rss_reg.register(
            RSSSource(name=REAL_RSS_SOURCE["name"], url=REAL_RSS_SOURCE["url"])
        )

        # Mark as inactive first
        status_service.mark_inactive(
            source_name=REAL_RSS_SOURCE["name"],
            source_type="rss",
            error_message="Previous error",
        )

        # Now try to reactivate - should trigger real HTTP validation
        result = status_service.mark_active(
            source_name=REAL_RSS_SOURCE["name"],
            source_type="rss",
        )

        # Should succeed because TechCrunch RSS is really accessible
        assert result is True, "Re-activation should succeed for valid source"

        # Verify status is now active
        status = status_service.get_status(REAL_RSS_SOURCE["name"])
        assert status is not None
        assert status.is_active is True
        assert status.error_message is None

        print(f"\n✅ Re-activated with validation: {status.source_name}")

    def test_mark_active_fails_for_invalid_source(self, status_service, real_registries):
        """Verify that re-activation FAILS when source is no longer valid.

        This tests the defensive re-validation logic: even if admin tries to
        reactivate, the system must confirm source is still accessible.
        """
        rss_reg, _, _ = real_registries

        # Register a FAKE source that doesn't exist
        fake_source = RSSSource(
            name="fake_source",
            url="https://this-domain-definitely-does-not-exist-12345.com/feed",
        )
        rss_reg.register(fake_source)

        # Try to reactivate - should FAIL validation
        result = status_service.mark_active(
            source_name="fake_source",
            source_type="rss",
        )

        assert result is False, "Re-activation should fail for invalid source"

        # Verify status remains inactive with error message
        status = status_service.get_status("fake_source")
        assert status is not None
        assert status.is_active is False
        assert status.error_message is not None
        assert len(status.error_message) > 0

        print(f"\n✅ Re-activation correctly failed: {status.error_message}")


# ==============================================================================
# Stage 4: Atomic Write & Persistence Verification
# ==============================================================================

@pytest.mark.integration
@pytest.mark.slow
class TestStage4_Persistence:
    """Stage 4: Verify atomic write and file structure (T106)."""

    def test_atomic_write_creates_valid_json(self, status_service):
        """Verify that source_status.json is valid JSON after writes."""
        # Perform multiple writes
        status_service.mark_inactive("src1", "rss", "Error 1")
        status_service.mark_inactive("src2", "github", "Error 2")
        status_service.mark_inactive("src3", "huggingface", "Error 3")

        # Read file directly (not through storage)
        assert STATUS_FILE.exists()
        with open(STATUS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Verify structure
        assert isinstance(data, dict)
        assert len(data) == 3
        assert "src1" in data
        assert "src2" in data
        assert "src3" in data

        # Verify each entry has required fields
        for name, status_data in data.items():
            assert "source_name" in status_data
            assert "source_type" in status_data
            assert "is_active" in status_data
            assert status_data["is_active"] is False

        print(f"\n✅ Atomic write verified: {len(data)} entries persisted")

    def test_no_temp_files_left_behind(self, status_service):
        """Verify that atomic write doesn't leave .tmp files behind."""
        status_service.mark_inactive("test_source", "rss", "Test error")

        # Check for any .tmp files in data directory
        if DATA_DIR.exists():
            tmp_files = list(DATA_DIR.glob("*.tmp"))
            assert len(tmp_files) == 0, f"Found leftover .tmp files: {tmp_files}"

        print("\n✅ No .tmp files left behind (atomic write clean)")

    def test_get_all_statuses(self, status_service):
        """Verify retrieval of all tracked statuses."""
        status_service.mark_inactive("src_a", "rss", "Error A")
        status_service.mark_inactive("src_b", "github", "Error B")

        all_statuses = status_service.get_all_statuses()

        assert len(all_statuses) == 2
        names = {s.source_name for s in all_statuses}
        assert "src_a" in names
        assert "src_b" in names

        print(f"\n✅ Retrieved {len(all_statuses)} statuses from storage")


# ==============================================================================
# Stage 5: Full End-to-End Workflow
# ==============================================================================

@pytest.mark.integration
@pytest.mark.slow
class TestStage5_EndToEnd:
    """Stage 5: Execute the full workflow from validation → config → status."""

    def test_full_workflow_new_source(
            self, config_service, status_service, real_registries
    ):
        """Complete workflow: validate → register → simulate failure → reactivate.

        This is the MASTER test that exercises the full Sprint 08 pipeline.
        """
        print("\n" + "=" * 70)
        print("🎬 FULL END-TO-END WORKFLOW")
        print("=" * 70)

        rss_reg, _, _ = real_registries
        source_name = "e2e_test_rss"
        source_url = REAL_RSS_SOURCE["url"]

        # Step 1: Pre-flight validation
        print("\n[Step 1] Pre-flight validation...")
        validator = RSSValidator(timeout=15.0)
        validation_result = validator.validate(RSSSource(name=source_name, url=source_url))
        assert validation_result.is_valid is True
        print(f"  ✓ Source validated: {source_url}")

        # Step 2: Register via Config Service
        print("\n[Step 2] Register via SourceConfigService...")
        config_result = config_service.update_source(
            source_type="rss",
            name=source_name,
            config={"url": source_url},
        )
        assert config_result.is_valid is True
        print(f"  ✓ Source registered in registry")

        # Step 3: Simulate runtime failure
        print("\n[Step 3] Simulate runtime failure...")
        status_service.mark_inactive(
            source_name=source_name,
            source_type="rss",
            error_message="Connection timeout (simulated)",
        )

        status = status_service.get_status(source_name)
        assert status.is_active is False
        print(f"  ✓ Source marked inactive: {status.error_message}")

        # Step 4: Admin tries to reactivate
        print("\n[Step 4] Admin attempts re-activation...")
        reactivation_result = status_service.mark_active(
            source_name=source_name,
            source_type="rss",
        )
        assert reactivation_result is True
        print(f"  ✓ Re-activation successful (source still valid)")

        # Step 5: Verify final state
        print("\n[Step 5] Verify final state...")
        final_status = status_service.get_status(source_name)
        assert final_status.is_active is True
        assert final_status.error_message is None
        print(f"  ✓ Source is active and healthy")

        # Step 6: Verify file persistence
        print("\n[Step 6] Verify file persistence...")
        assert STATUS_FILE.exists()
        with open(STATUS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert source_name in data
        assert data[source_name]["is_active"] is True
        print(f"  ✓ State persisted to {STATUS_FILE}")

        print("\n" + "=" * 70)
        print("🎉 END-TO-END WORKFLOW COMPLETED SUCCESSFULLY")
        print("=" * 70)


# ==============================================================================
# Execution
# ==============================================================================

if __name__ == "__main__":
    # Allow running directly with: python -m tests.integration.test_real_workflow_s08
    pytest.main([__file__, "-v", "-s", "-m", "integration"])
