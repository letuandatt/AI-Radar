"""Feedback endpoints reuse the existing authentication and origin boundary."""

import asyncio

from fastapi import APIRouter, HTTPException, Request

from app.api.v1.routes import services
from app.services.feedback.models import FeedbackRequest, UserFeedback, UserPreferences

router = APIRouter(prefix="/api/v1")


def feedback_service(request: Request):
    """Reject runtimes where feedback has not been wired."""
    service = services(request).feedback
    if service is None:
        raise HTTPException(503, "Feedback is unavailable in this runtime")
    return service


@router.get(
    "/knowledge/{item_id}/feedback", operation_id="getFeedback", response_model=UserFeedback
)
async def get_feedback(request: Request, item_id: str):
    """Read the current choice without creating a feedback record."""
    try:
        return await asyncio.to_thread(feedback_service(request).get_feedback, item_id)
    except LookupError as error:
        raise HTTPException(404, "Knowledge item not found") from error


@router.put(
    "/knowledge/{item_id}/feedback", operation_id="setFeedback", response_model=UserFeedback
)
async def set_feedback(request: Request, item_id: str, body: FeedbackRequest):
    """Set an absolute choice, or clear it with null; no implicit toggle or model call."""
    if (
        request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        != "application/json"
    ):
        raise HTTPException(415, "JSON required")
    try:
        return await asyncio.to_thread(feedback_service(request).record_feedback, item_id, body)
    except LookupError as error:
        raise HTTPException(404, "Knowledge item not found") from error


@router.get(
    "/feedback/preferences", operation_id="getFeedbackPreferences", response_model=UserPreferences
)
async def get_preferences(request: Request):
    """Summarize the single reader's explicit choices on live articles."""
    return await asyncio.to_thread(feedback_service(request).get_user_preferences)
