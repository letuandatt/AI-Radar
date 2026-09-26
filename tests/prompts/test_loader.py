from pathlib import Path

import pytest

from app.prompts.loader import PromptLoader, PromptNotFoundError


def test_load_existing_prompt(tmp_path: Path):
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    analysis_dir = prompts_dir / "analysis"
    analysis_dir.mkdir()
    (analysis_dir / "test.md").write_text("Hello {name}", encoding="utf-8")

    loader = PromptLoader(base_dir=prompts_dir)
    content = loader.load("analysis/test")
    assert content == "Hello {name}"


def test_load_caches_prompt(tmp_path: Path):
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    (prompts_dir / "test.md").write_text("V1", encoding="utf-8")

    loader = PromptLoader(base_dir=prompts_dir)
    loader.load("test")

    (prompts_dir / "test.md").write_text("V2", encoding="utf-8")
    assert loader.load("test") == "V1"


def test_raises_on_missing_prompt(tmp_path: Path):
    loader = PromptLoader(base_dir=tmp_path)
    with pytest.raises(PromptNotFoundError):
        loader.load("nonexistent")
