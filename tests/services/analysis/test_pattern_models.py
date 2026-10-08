"""Validate evidence, confidence, descriptions and observation timestamps."""

from datetime import timedelta

import pytest
from pydantic import ValidationError

from app.services.analysis.models import DiscoveredPattern, PatternSnapshot
from tests.fakes.analysis import NOW
from tests.fakes.patterns import pattern


@pytest.mark.parametrize(
    "update",
    [
        {"description": "  "},
        {"confidence": -0.1},
        {"confidence": 1.1},
        {"confidence": float("nan")},
        {"evidence_ids": []},
        {"evidence_ids": ["a", "a"]},
        {"pattern_type": "unknown"},
        {"first_detected": NOW.replace(tzinfo=None)},
    ],
)
def test_invalid_patterns(update):
    with pytest.raises(ValidationError):
        DiscoveredPattern.model_validate(pattern().model_dump() | update)


def test_snapshot_cannot_precede_first_detection():
    with pytest.raises(ValidationError):
        PatternSnapshot(**pattern().model_dump(), observed_at=NOW - timedelta(seconds=1))
