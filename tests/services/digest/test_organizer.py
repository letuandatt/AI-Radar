"""Editorial rules and generator wiring with local SQLite and fake upstream LLMs."""

import json
from unittest.mock import MagicMock

import pytest

from app.config.importance import ImportanceConfig
from app.services.digest.config import DigestConfig
from app.services.digest.models import DailyDigest, DigestItem, DigestSection, topic_groups
from app.services.digest.organizer import ContentOrganizer
from tests.services.digest.test_generator import digest_env as digest_env
from tests.services.intelligence.conftest import DAY
from tests.services.intelligence.conftest import environment as environment
from tests.services.intelligence.test_refiner import prepared as prepared


@pytest.fixture
def unordered_digest(digest_env):
    """Build all four categories with deliberately unsorted items and shared topics."""
    digest = digest_env[3].generate(DAY)
    template = digest.sections[0].items[0].model_dump()
    sections = []
    for category in ("others", "news", "github", "papers"):
        items = []
        for suffix, score in (("low", 0.7), ("b", 0.9), ("a", 0.9)):
            items.append(
                DigestItem.model_validate(
                    {
                        **template,
                        "knowledge_id": f"{category}-{suffix}",
                        "source_type": "github" if category == "github" else "rss",
                        "source_name": category,
                        "importance_score": score,
                        "summary": "Long summary " * 30,
                        "topics": ["shared", category],
                    }
                )
            )
        sections.append(
            DigestSection(
                section_id=f"section-{category}",
                section_title="Original heading",
                category=category,
                items=items,
            )
        )
    return DailyDigest.model_validate(
        {
            **digest.model_dump(),
            "sections": sections,
            "topic_groups": topic_groups(sections),
            "total_items": 12,
            "candidate_count": 12,
            "eligible_count": 12,
            "unmapped_count": 0,
            "config": DigestConfig(
                importance=ImportanceConfig(
                    digest_source_categories={"rss:papers": "papers", "rss:news": "news"},
                    threshold_papers=0,
                    threshold_github=0,
                    threshold_news=0,
                ),
                others_threshold=0,
            ),
        }
    )


def test_section_order_headers_and_item_ties(unordered_digest):
    result = ContentOrganizer().organize(unordered_digest)
    assert [s.category for s in result.sections] == ["papers", "github", "news", "others"]
    assert [s.section_title for s in result.sections] == [
        "📄 Papers",
        "💻 GitHub",
        "📰 News",
        "📦 Others",
    ]
    for section in result.sections:
        assert section.section_id == f"section-{section.category}"
        assert [i.knowledge_id for i in section.items] == [
            f"{section.category}-a",
            f"{section.category}-b",
            f"{section.category}-low",
        ]
    assert result.topic_groups["shared"] == [
        f"{category}-{suffix}"
        for category in ("papers", "github", "news", "others")
        for suffix in ("a", "b", "low")
    ]


@pytest.mark.parametrize("summary", ["", "Short summary", "é" * 199, "文" * 200, "🚀" * 201])
def test_summary_boundaries(unordered_digest, summary):
    unordered_digest.sections[0].items[0].summary = summary
    result = ContentOrganizer().organize(unordered_digest)
    item = next(i for s in result.sections for i in s.items if i.knowledge_id == "others-low")
    expected = summary if len(summary) <= 200 else summary[:199] + "…"
    assert item.summary == expected
    assert all(len(i.summary) <= 200 for s in result.sections for i in s.items)


def test_truncation_removes_space_before_ellipsis(unordered_digest):
    unordered_digest.sections[0].items[0].summary = "x" * 198 + " " + "tail"
    result = ContentOrganizer().organize(unordered_digest)
    assert result.sections[-1].items[-1].summary == "x" * 198 + "…"


def test_preserves_input_identity_provenance_and_selection(unordered_digest):
    original = unordered_digest.model_dump()
    result = ContentOrganizer().organize(unordered_digest)
    assert unordered_digest.model_dump() == original
    assert result.model_dump(exclude={"sections", "topic_groups"}) == unordered_digest.model_dump(
        exclude={"sections", "topic_groups"}
    )
    originals = {i.knowledge_id: i for s in unordered_digest.sections for i in s.items}
    for section in result.sections:
        for item in section.items:
            assert item.model_dump(exclude={"summary"}) == originals[item.knowledge_id].model_dump(
                exclude={"summary"}
            )
    result.sections[0].items[0].topics.append("result-only")
    result.config.importance.digest_source_categories["rss:new"] = "news"
    result.intelligence.sections[0].content = "result-only"
    assert unordered_digest.model_dump() == original


def test_idempotent_and_independent_of_input_order(unordered_digest):
    organizer = ContentOrganizer()
    first = organizer.organize(unordered_digest)
    assert organizer.organize(first) == first
    unordered_digest.sections.reverse()
    for section in unordered_digest.sections:
        section.items.reverse()
    unordered_digest.topic_groups = topic_groups(unordered_digest.sections)
    assert organizer.organize(unordered_digest) == first
    assert DailyDigest.model_validate_json(first.model_dump_json()) == first


@pytest.mark.parametrize("empty_all", [False, True])
def test_empty_sections_are_removed_without_losing_items(unordered_digest, empty_all):
    emptied = unordered_digest.sections if empty_all else unordered_digest.sections[:1]
    for section in emptied:
        section.items = []
    unordered_digest.total_items = sum(len(s.items) for s in unordered_digest.sections)
    unordered_digest.topic_groups = topic_groups(unordered_digest.sections)
    result = ContentOrganizer().organize(unordered_digest)
    assert result.total_items == (0 if empty_all else 9)
    assert len(result.sections) == (0 if empty_all else 3)
    assert all(s.items for s in result.sections)
    if empty_all:
        assert result.topic_groups == {}
        assert ContentOrganizer().organize(result) == result
    assert all(not s.items for s in emptied)


@pytest.mark.parametrize("field,value", [("total_items", 999), ("topic_groups", {"bad": ["x"]})])
def test_invalid_input_is_rejected_not_silently_repaired(unordered_digest, field, value):
    setattr(unordered_digest, field, value)
    with pytest.raises(ValueError):
        ContentOrganizer().organize(unordered_digest)


def test_generator_organizes_before_persistence_and_preserves_source(digest_env):
    store, access, _, generator, _ = digest_env
    conn = store._conn_manager.get_connection()
    with conn:
        rows = conn.execute("SELECT id, metadata_json FROM knowledge_objects").fetchall()
        for identity, payload in rows:
            metadata = json.loads(payload)
            metadata["summary"] = "Source summary " * 30
            conn.execute(
                "UPDATE knowledge_objects SET metadata_json=? WHERE id=?",
                (json.dumps(metadata), identity),
            )
    result = generator.generate(DAY)
    assert result.sections[0].section_title == "📰 News"
    assert all(len(i.summary) == 200 and i.summary.endswith("…") for i in result.sections[0].items)
    assert access.get_digest(DAY) == result
    assert generator.get_digest(DAY) == result
    assert all(
        len(store.get_by_id(i.knowledge_id).metadata.summary) > 200
        for i in result.sections[0].items
    )


def test_legacy_cache_is_unchanged_until_explicit_rebuild(digest_env, monkeypatch):
    _, access, _, generator, _ = digest_env
    legacy = generator.generate(DAY)
    legacy.sections[0].section_title = "News"
    legacy.sections[0].items[0].summary = "Legacy summary " * 30
    inputs = access.load_digest_inputs(DAY)
    legacy = access.save_digest(
        legacy, fingerprint=inputs["fingerprint"], rebuild=True, expected_id=legacy.digest_id
    )
    organizer = generator._organizer.organize
    blocked = MagicMock(side_effect=AssertionError("Cache must not be restyled"))
    monkeypatch.setattr(generator._organizer, "organize", blocked)
    assert generator.generate(DAY) == legacy
    assert generator.get_digest(DAY) == legacy
    blocked.assert_not_called()
    monkeypatch.setattr(generator._organizer, "organize", organizer)
    rebuilt = generator.generate(DAY, rebuild=True)
    assert rebuilt.digest_id != legacy.digest_id
    assert rebuilt.sections[0].section_title == "📰 News"
    assert access.get_digest(DAY) == rebuilt


def test_organization_failure_preserves_old_snapshot(digest_env, monkeypatch):
    _, access, _, generator, _ = digest_env
    saved = generator.generate(DAY)
    monkeypatch.setattr(
        generator._organizer, "organize", MagicMock(side_effect=ValueError("Invalid organization"))
    )
    with pytest.raises(ValueError, match="Invalid organization"):
        generator.generate(DAY, rebuild=True)
    assert access.get_digest(DAY) == saved
