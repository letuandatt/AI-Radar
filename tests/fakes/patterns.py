"""Typed temporal fixtures and a deterministic structured-description fake."""

import json
from datetime import timedelta
from html import unescape

from app.services.analysis.models import (
    DiscoveredPattern,
    ObservedKnowledgeItem,
    PatternDescriptions,
)
from tests.fakes.analysis import NOW, make_analysis


def observed(index, days_ago=1, topic="RAG", at=None):
    item = make_analysis(index, str(index % 3), [topic], at=NOW)
    return ObservedKnowledgeItem(
        **item.model_dump(), first_observed_at=at or NOW - timedelta(days=days_ago)
    )


def hundred_items():
    rows = []
    for topic, ages in [
        ("new", [1] * 10),
        ("steady", [1] * 5 + [8] * 5 + [15] * 5 + [22] * 5),
        ("falling", [15] * 10 + [40] * 30),
        ("neutral", [5] * 15 + [35] * 14 + [59]),
    ]:
        for age in ages:
            rows.append(observed(len(rows), age, topic))
    return rows


def describe(prompt, schema):
    assert schema is PatternDescriptions
    payload = prompt.split("<untrusted_data>\n", 1)[1].split("\n</untrusted_data>", 1)[0]
    candidates = json.loads(unescape(payload))
    return PatternDescriptions(
        descriptions=[
            {"pattern_id": row["pattern_id"], "description": f"Quan sát {row['topic']} từ dữ liệu."}
            for row in candidates
        ]
    )


def pattern(pattern_id="pattern-1", topic="theme:rag"):
    return DiscoveredPattern(
        pattern_id=pattern_id,
        pattern_type="emerging",
        topic=topic,
        time_window_days=30,
        description="Một chủ đề mới trong dữ liệu.",
        confidence=0.8,
        evidence_ids=["ko-1"],
        first_detected=NOW,
        metrics={"recent_count": 1},
    )


def thousand_items():
    return [
        item.model_copy(update={"knowledge_id": f"ko-{batch * 100 + index}"})
        for batch in range(10)
        for index, item in enumerate(hundred_items())
    ]
