"""Auditable scoring contracts; observations do not guarantee ingestion completeness."""

from datetime import timedelta
from enum import Enum
from math import isclose, isfinite
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from app.config.importance import DigestCategory
from app.models.knowledge_object import KnowledgeObject
from app.services.analysis.models import AnalyzedKnowledgeItem
from app.services.importance.config import ImportanceConfig, Unit
from app.services.trend.models import TrendRun, TrendSnapshot, week_start

SignalStatus = Literal["observed", "missing", "not_applicable", "defaulted"]


class ImportanceInputs(BaseModel):
    """One consistent repository read, including candidate and window analyses."""

    objects: list[KnowledgeObject]
    analyses: list[AnalyzedKnowledgeItem]
    trend_run: TrendRun | None
    trends: list[TrendSnapshot]


class ScoreContext(BaseModel):
    """Explain evidence and dates without interpreting missing data as observed zero.

    Cross-source uses analyzed_at in [window_start, window_end]. Entity popularity
    uses the newest completed UTC ISO week; it is not intrinsic entity authority.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    window_start: AwareDatetime
    window_end: AwareDatetime
    trend_week: str
    trend_computed_at: AwareDatetime | None = None
    observed_items: int = Field(ge=0)
    matched_source_count: int = Field(ge=0)
    entity_matches: list[str]
    published_at: AwareDatetime | None
    publication_assumed_utc: bool = False
    publication_in_future: bool = False
    github_stars: int | None = Field(default=None, ge=0, strict=True)
    source_label: str


class LLMImportanceScore(BaseModel):
    """One bounded refinement response; identity must match the requested item."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    knowledge_id: str = Field(min_length=1)
    score: Unit
    reason: str = Field(min_length=1, max_length=1000)


class ImportanceScore(BaseModel):
    """Latest score per knowledge item; reruns replace rather than duplicate it.

    Rule-only results retain rule_score. Refined results use 70% rule and 30% LLM.
    Persisted config and context make the score interpretable after policy changes.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
    knowledge_id: str = Field(min_length=1)
    computed_at: AwareDatetime
    rule_score: Unit
    final_score: Unit
    components: dict[str, Unit]
    component_status: dict[str, SignalStatus]
    config: ImportanceConfig
    context: ScoreContext
    score_version: Literal["v1"] = "v1"
    llm_adjusted: bool = False
    llm_score: Unit | None = None
    llm_reason: str | None = None

    @model_validator(mode="after")
    def validate_formula(self) -> "ImportanceScore":
        """Reject contradictory components, refinement flags and window context."""
        keys = set(self.config.weights)
        if set(self.components) != keys or set(self.component_status) != keys:
            raise ValueError("Exactly six named components and statuses are required")
        expected = sum(self.config.weights[key] * self.components[key] for key in keys)
        if not isclose(self.rule_score, expected, rel_tol=0, abs_tol=1e-12):
            raise ValueError("rule_score must match weighted components")
        if self.llm_adjusted != (self.llm_score is not None):
            raise ValueError("llm_adjusted must match llm_score availability")
        if self.llm_adjusted != bool(self.llm_reason and self.llm_reason.strip()):
            raise ValueError("Only refined scores have a nonempty LLM reason")
        final = 0.7 * expected + 0.3 * self.llm_score if self.llm_score is not None else expected
        if not isclose(self.final_score, final, rel_tol=0, abs_tol=1e-12):
            raise ValueError("final_score must match the refinement formula")
        for key, status in self.component_status.items():
            if status in {"missing", "not_applicable"} and self.components[key] != 0:
                raise ValueError("Unavailable signals must contribute zero")
        context = self.context
        if (
            context.window_end != self.computed_at
            or context.window_end - context.window_start
            != timedelta(days=self.config.cross_source_days)
            or week_start(context.trend_week) + timedelta(days=7) > self.computed_at
        ):
            raise ValueError("Invalid score context window")
        return self


class RelevanceAssessment(BaseModel):
    """Topic fit against at most five retrieved neighbors, not a calibrated probability.

    base_relevance comes from the saved extraction component of ImportanceScore.
    Topic consistency is mean Jaccard overlap over neighbors with nonempty topics.
    Missing context preserves the base score and is excluded from irrelevant scans.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
    knowledge_id: str = Field(min_length=1)
    assessed_at: AwareDatetime
    relevance_score: Unit
    related_items: list[str] = Field(max_length=5)
    topic_consistency: Unit | None
    base_relevance: Unit
    status: Literal["assessed", "insufficient_context"]
    reason: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_assessment(self) -> "RelevanceAssessment":
        """Keep missing evidence distinct from observed zero overlap."""
        ids = self.related_items
        if any(not value.strip() or value == self.knowledge_id for value in ids):
            raise ValueError("Related IDs must be nonblank and exclude the assessed item")
        if len(ids) != len(set(ids)):
            raise ValueError("Related IDs must be unique")
        if self.status == "assessed":
            if not ids or self.topic_consistency is None:
                raise ValueError("Assessed results require neighbors and topic consistency")
            expected = 0.7 * self.base_relevance + 0.3 * self.topic_consistency
        else:
            if self.topic_consistency is not None:
                raise ValueError("Insufficient context requires unknown topic consistency")
            expected = self.base_relevance
        if not isclose(self.relevance_score, expected, rel_tol=0, abs_tol=1e-12):
            raise ValueError("Relevance score must match the assessment formula")
        return self


class PriorityLevel(str, Enum):
    """Fixed score bands, independent of digest policy; ARCHIVE never deletes data."""

    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    ARCHIVE = "ARCHIVE"

    @property
    def threshold(self) -> float:
        """Inclusive lower bound; also defines the explicit priority ordering."""
        return {
            PriorityLevel.CRITICAL: 0.9,
            PriorityLevel.HIGH: 0.75,
            PriorityLevel.MEDIUM: 0.6,
            PriorityLevel.LOW: 0.4,
            PriorityLevel.ARCHIVE: 0.0,
        }[self]

    @classmethod
    def from_score(cls, score: float) -> "PriorityLevel":
        """Classify the original finite score without rounding."""
        if not isfinite(score) or not 0 <= score <= 1:
            raise ValueError("Priority score must be finite and between 0 and 1")
        return next(level for level in cls if score >= level.threshold)


class PriorityEvaluation(BaseModel):
    """Evaluate a saved final score using current digest policy.

    threshold_applied is the priority band's lower bound. Unknown digest
    categories leave all three digest fields None, distinct from ineligibility.
    This result does not refresh scores, select a digest, or archive an item.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
    knowledge_id: str = Field(min_length=1)
    priority: PriorityLevel
    score: Unit
    threshold_applied: Unit
    reason: str = Field(min_length=1)
    digest_category: DigestCategory | None = None
    digest_threshold: Unit | None = None
    digest_eligible: bool | None = Field(default=None, strict=True)

    @model_validator(mode="after")
    def validate_decision(self) -> "PriorityEvaluation":
        """Reject contradictory bands, thresholds and digest decisions."""
        if (
            self.priority != PriorityLevel.from_score(self.score)
            or self.threshold_applied != self.priority.threshold
        ):
            raise ValueError("Priority and threshold must match the score band")
        if self.digest_category is None:
            if self.digest_threshold is not None or self.digest_eligible is not None:
                raise ValueError("Unknown digest category requires unknown eligibility")
        elif self.digest_threshold is None or self.digest_eligible != (
            self.score >= self.digest_threshold
        ):
            raise ValueError("Known digest category requires a matching threshold decision")
        return self
