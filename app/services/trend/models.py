"""Weekly trend contracts; counts describe observed data, not ingestion coverage."""

import json
from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import NAMESPACE_URL, uuid5

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

TrendType = Literal["topic", "source", "entity"]


def week_start(week: str) -> datetime:
    """Parse canonical ISO YYYY-Www into Monday 00:00 UTC, rejecting invalid weeks."""
    try:
        year, number = week.split("-W")
        start = datetime.fromisocalendar(int(year), int(number), 1).replace(tzinfo=timezone.utc)
        if week != week_label(start):
            raise ValueError
        return start
    except (ValueError, TypeError, AttributeError) as error:
        raise ValueError("Expected a valid ISO week in YYYY-Www format") from error


def week_label(value: datetime) -> str:
    """Return an ISO week label for a timezone-aware instant in UTC."""
    if value.utcoffset() is None:
        raise ValueError("Expected a timezone-aware datetime")
    year, week, _ = value.astimezone(timezone.utc).isocalendar()
    return f"{year:04d}-W{week:02d}"


def trend_identity(kind: str, name: str) -> str:
    """Create a stable identity independent of week, input order and counts."""
    return str(uuid5(NAMESPACE_URL, json.dumps(["ai-radar:trend", kind, name])))


class Trend(BaseModel):
    """One distinct signal, counted once per live analyzed knowledge object.

    Topic names are normalized themes. Entity names retain their typed namespace
    (models:, companies:, people:). Source names are escaped source_type:name pairs.
    Counts use first analysis persistence in UTC ISO weeks [start, end), with
    current labels: re-analysis can change labels but never moves the item week.
    baseline_empty means the entire baseline cohort has no observed items; it is
    not proof of no activity. new means absent only in this comparison's baseline.
    Score v1 uses within-type cohorts before filtering: delta/100 clipped to
    [-1, 1] (new=1, baseline_empty=0), count/max_current_count, and rank change
    divided by max(candidate_count-1, 1). Ranks are competition ranks by count,
    including zero-count candidates. Weights are 0.6, 0.3, 0.1 respectively.
    """

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, frozen=True)
    trend_id: str
    type: TrendType
    name: str = Field(min_length=1)
    current_count: int = Field(ge=0)
    baseline_count: int = Field(ge=0)
    delta_percent: float | None
    comparison: Literal["comparable", "new", "baseline_empty"]
    rank_change: int
    normalized_delta: float = Field(ge=-1, le=1)
    normalized_count: float = Field(ge=0, le=1)
    rank_bonus: float = Field(ge=-1, le=1)
    trend_score: float = Field(ge=-1, le=1)
    sample_knowledge_ids: list[str] = Field(max_length=5)

    @model_validator(mode="after")
    def validate_identity_and_delta(self) -> "Trend":
        """Reject inconsistent identity, percentage, score or duplicate evidence."""
        if self.trend_id != trend_identity(self.type, self.name):
            raise ValueError("trend_id must match type and name")
        if not self.current_count and not self.baseline_count:
            raise ValueError("A candidate must have evidence in at least one week")
        if self.baseline_count:
            expected = (self.current_count - self.baseline_count) / self.baseline_count * 100
            if (
                self.comparison != "comparable"
                or self.delta_percent is None
                or abs(self.delta_percent - expected) > 1e-9
            ):
                raise ValueError("Invalid baseline comparison")
        elif self.delta_percent is not None or self.comparison == "comparable":
            raise ValueError("A zero baseline has no defined percentage")
        expected_score = (
            0.6 * self.normalized_delta + 0.3 * self.normalized_count + 0.1 * self.rank_bonus
        )
        if abs(self.trend_score - expected_score) > 1e-9:
            raise ValueError("trend_score must match its components")
        if len(self.sample_knowledge_ids) != len(set(self.sample_knowledge_ids)):
            raise ValueError("Evidence IDs must be unique")
        return self


class TrendRun(BaseModel):
    """A successful computation, persisted even when there are no candidates.

    Missing run != empty run. Totals count observed live analyses, not configured
    source coverage or ingest completeness. Recomputing replaces that week's
    snapshots atomically. Historical labels reflect the data at computed_at.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    week: str
    baseline_week: str
    computed_at: AwareDatetime
    current_items: int = Field(ge=0)
    baseline_items: int = Field(ge=0)
    snapshot_count: int = Field(ge=0)
    min_count: int = Field(ge=1)
    score_version: Literal["v1"] = "v1"

    @field_validator("week", "baseline_week")
    @classmethod
    def validate_week(cls, value: str) -> str:
        """Accept canonical ISO weeks only."""
        week_start(value)
        return value

    @model_validator(mode="after")
    def validate_periods(self) -> "TrendRun":
        """Both periods must be complete and baseline must precede current."""
        current = week_start(self.week)
        if week_start(self.baseline_week) >= current:
            raise ValueError("baseline_week must precede week")
        if current + timedelta(days=7) > self.computed_at:
            raise ValueError("Only completed UTC weeks can be persisted")
        return self


class TrendSnapshot(Trend):
    """An unfiltered candidate; includes disappearing and below-threshold signals."""

    snapshot_id: str
    week: str
    baseline_week: str
    computed_at: AwareDatetime

    @model_validator(mode="after")
    def validate_snapshot(self) -> "TrendSnapshot":
        """Keep weekly identity stable across reruns."""
        week_start(self.week)
        week_start(self.baseline_week)
        expected = str(uuid5(NAMESPACE_URL, f"{self.trend_id}:{self.week}"))
        if self.snapshot_id != expected:
            raise ValueError("snapshot_id must match trend_id and week")
        return self


class WeeklyTrendReport(TrendRun):
    """Returned trend pass min_count; snapshot_count includes ALL candidates."""

    trends: list[Trend]
