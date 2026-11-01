"""Validated importance policy; defaults are initial heuristics, not calibrated probabilities."""

from math import isclose
from typing import Annotated, Literal
from urllib.parse import quote, unquote

from pydantic import BaseModel, ConfigDict, Field, model_validator

Unit = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]
DigestCategory = Literal["papers", "github", "news"]


class ImportanceConfig(BaseModel):
    """Fixed weights; missing signals do not redistribute their weight.

    Authority keys are escaped source_type:name labels, identical to S19.
    An absent key uses default_authority and is explicitly marked defaulted.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
    weight_relevance: Unit = 0.4
    weight_freshness: Unit = 0.2
    weight_authority: Unit = 0.15
    weight_github_stars: Unit = 0.1
    weight_cross_source: Unit = 0.1
    weight_entity: Unit = 0.05
    llm_top_n: int = Field(default=30, ge=0, strict=True)
    max_age_days: float = Field(default=7, gt=0)
    stars_cap: int = Field(default=10_000, ge=1, strict=True)
    source_cap: int = Field(default=5, ge=2, strict=True)
    cross_source_days: int = Field(default=7, ge=1, le=365, strict=True)
    source_authorities: dict[str, Unit] = Field(default_factory=dict)
    default_authority: Unit = 0.5
    threshold_papers: Unit = 0.7
    threshold_github: Unit = 0.6
    threshold_news: Unit = 0.65

    # Exact escaped source_type:source_name keys; GitHub is recognized directly.
    digest_source_categories: dict[str, DigestCategory] = Field(default_factory=dict)

    @property
    def weights(self) -> dict[str, float]:
        """Expose the six named components in formula order."""
        return {
            "relevance_score": self.weight_relevance,
            "freshness": self.weight_freshness,
            "source_authority": self.weight_authority,
            "github_stars": self.weight_github_stars,
            "cross_source_mentions": self.weight_cross_source,
            "entity_importance": self.weight_entity,
        }

    @model_validator(mode="after")
    def validate_weights(self) -> "ImportanceConfig":
        """Reject invalid policies before reading data or calling a provider."""
        if not isclose(sum(self.weights.values()), 1.0, rel_tol=0, abs_tol=1e-12):
            raise ValueError("Importance weights must sum to 1")
        if any(not key.strip() or ":" not in key for key in self.source_authorities):
            raise ValueError("Authority keys must be escaped source_type:name labels")
        for key, category in self.digest_source_categories.items():
            parts = key.split(":")
            if len(parts) != 2 or any(
                not unquote(part).strip() or quote(unquote(part), safe="") != part for part in parts
            ):
                raise ValueError(
                    "Digest mapping keys must be escaped source_type:source_name labels"
                )
            if parts[0] == "github" and category != "github":
                raise ValueError("GitHub sources must use the github digest category")
        return self
