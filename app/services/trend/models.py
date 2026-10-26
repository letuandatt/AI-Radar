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


class WeeklyCount(BaseModel):
    """Window-relative count from a completed UTC week's persisted run.

    missing_run has count=None. empty_run has count=0 but no observed cohort.
    observed means the run had analyzed items; an absent signal then counts as 0.
    None of these states guarantees complete source ingestion.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    week: str
    count: int | None = Field(ge=0)
    status: Literal["observed", "empty_run", "missing_run"]

    @model_validator(mode="after")
    def validate_observation(self) -> "WeeklyCount":
        """Keep unavailable data distinct from an observed zero."""
        week_start(self.week)
        if (self.count is None) != (self.status == "missing_run"):
            raise ValueError("Only missing_run has count=None")
        if self.status == "empty_run" and self.count != 0:
            raise ValueError("An empty run must have count=0")
        return self


class TrendEvolution(BaseModel):
    """Evolution of saved current_count values, never baseline backfills.

    Classification requires the entire requested window to be observed, with
    at least three consecutive weeks. Otherwise pattern/volatility are None.
    Volatility is population std_dev / mean, with 0 for an all-zero series.
    Such a series is no_activity, not evidence of a stable active trend.
    unclassified preserves cases outside the four specified pattern rules.
    """

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, frozen=True)
    trend_id: str
    type: TrendType
    name: str = Field(min_length=1)
    weekly_counts: list[WeeklyCount] = Field(min_length=1)
    observed_weeks: int = Field(ge=0)
    pattern: Literal["growing", "stable", "declining", "volatile"] | None
    volatility: float | None = Field(ge=0)
    status: Literal["classified", "insufficient_history", "no_activity", "unclassified"]

    @model_validator(mode="after")
    def validate_history(self) -> "TrendEvolution":
        """Validate identity, consecutive weeks and classification availability."""
        if self.trend_id != trend_identity(self.type, self.name):
            raise ValueError("trend_id must match type and name")
        starts = [week_start(point.week) for point in self.weekly_counts]
        if any(right - left != timedelta(days=7) for left, right in zip(starts, starts[1:])):
            raise ValueError("weekly_counts must be consecutive and chronological")
        observed = sum(point.status == "observed" for point in self.weekly_counts)
        if self.observed_weeks != observed:
            raise ValueError("observed_weeks must match weekly_counts")
        insufficient = observed != len(starts) or observed < 3
        if (self.status == "insufficient_history") != insufficient:
            raise ValueError("Classification requires a fully observed window of at least 3 weeks")
        if (self.pattern is not None) != (self.status == "classified"):
            raise ValueError("Only classified results have a pattern")
        if (self.volatility is None) != insufficient:
            raise ValueError("Volatility is unavailable for insufficient history")
        if not insufficient:
            inactive = all(point.count == 0 for point in self.weekly_counts)
            if (self.status == "no_activity") != inactive:
                raise ValueError("Only an all-zero observed series has no_activity")
            if inactive and self.volatility != 0:
                raise ValueError("All-zero volatility must be 0")
        return self
