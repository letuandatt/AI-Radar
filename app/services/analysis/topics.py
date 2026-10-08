"""Shared, deterministic topic identities for cross-source and temporal analysis."""

from collections.abc import Sequence
from urllib.parse import quote

from app.services.analysis.models import AnalyzedKnowledgeItem


def normalize_topic(value: str) -> str:
    """Normalize spelling without conflating themes with typed entities."""
    return " ".join(value.split()).casefold()


def topic_signals(item: AnalyzedKnowledgeItem) -> set[str]:
    """Return unique, namespaced topic keys for one knowledge item."""
    signals = {f"theme:{value}" for raw in item.themes if (value := normalize_topic(raw))}
    for kind, values in item.entities.model_dump().items():
        signals.update(f"{kind}:{value}" for raw in values if (value := normalize_topic(raw)))
    return signals


def source_labels(items: Sequence[AnalyzedKnowledgeItem]) -> list[str]:
    """Encode unique source pairs without separator collisions."""
    return sorted(
        {f"{quote(item.source_type, safe='')}:{quote(item.source_name, safe='')}" for item in items}
    )
