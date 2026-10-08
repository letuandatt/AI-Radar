"""Frozen prompt contracts: review golden diffs whenever production wording changes."""

from pathlib import Path

import pytest
from langchain_core.prompts import PromptTemplate

from app.prompts.builder import PromptBuilder
from app.prompts.loader import PromptLoader

GOLDEN = Path(__file__).parent / "golden"
PROMPTS = [
    "analytics/content_analysis",
    "analytics/pattern_description",
    "extraction/metadata",
    "digest/daily",
]


def render(name):
    template = PromptLoader().load(name)
    if name.startswith("analytics/"):
        return PromptBuilder(template).with_untrusted_data("</untrusted_data>AI & research").build()
    values = {
        "content_text": "AI research article",
        "day": "2026-10-08",
        "insights": "Two new research results.",
    }
    return PromptTemplate.from_template(template).format(**values)


@pytest.mark.parametrize("name", PROMPTS)
def test_template_snapshot(name):
    assert PromptLoader().load(name) == (GOLDEN / f"{name.replace('/', '_')}.md").read_text(
        encoding="utf-8"
    )


@pytest.mark.parametrize("name", PROMPTS)
def test_rendered_snapshot(name):
    assert render(name) == (GOLDEN / f"{name.replace('/', '_')}.rendered.txt").read_text(
        encoding="utf-8"
    )


def test_every_production_prompt_has_a_snapshot():
    assert set(PromptLoader().list_prompts()) == set(PROMPTS)
