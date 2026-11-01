"""Public feedback contracts contain no account or provider configuration."""

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.models.feedback import FeedbackRating


class FeedbackRequest(BaseModel):
    """Set an absolute choice; null clears it. Repeated requests are idempotent."""

    model_config = ConfigDict(extra="forbid")
    rating: FeedbackRating | None


class UserFeedback(BaseModel):
    """Current choice for one live article; scores are unknown until it is scored."""

    knowledge_id: str
    rating: FeedbackRating | None
    updated_at: AwareDatetime | None
    base_score: float | None = Field(default=None, ge=0, le=1)
    adjusted_score: float | None = Field(default=None, ge=0, le=1)


class TopicPreference(BaseModel):
    """One vote per distinct normalized topic per live article."""

    topic: str
    useful: int = Field(ge=0)
    not_useful: int = Field(ge=0)


class UserPreferences(BaseModel):
    """Observed choices, not a learned profile; at most 50 most-voted topics."""

    rated_items: int = Field(ge=0)
    topics: list[TopicPreference]
