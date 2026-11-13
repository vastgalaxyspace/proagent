from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


ReviewDecision = Literal[
    "approved",
    "changes_requested",
    "rejected",
]
ReviewTargetType = Literal["field", "requirement"]


class ReviewCorrection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_type: ReviewTargetType
    target_key: str = Field(min_length=1, max_length=255)
    patch: dict[str, Any] = Field(min_length=1)
    reason: str = Field(min_length=1, max_length=2000)


class ReviewDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: ReviewDecision
    comment: str | None = Field(default=None, max_length=5000)
    corrections: list[ReviewCorrection] = Field(
        default_factory=list,
        max_length=500,
    )

    @model_validator(mode="after")
    def validate_decision(self) -> "ReviewDecisionRequest":
        comment = (self.comment or "").strip()
        if self.decision in {"changes_requested", "rejected"} and not comment:
            raise ValueError(
                "A comment is required when changes are requested or the tender is rejected."
            )
        if self.decision == "rejected" and self.corrections:
            raise ValueError("Rejected reviews cannot include corrections.")
        return self


class ReviewResumeCommand(ReviewDecisionRequest):
    reviewer_user_id: str = Field(min_length=1, max_length=100)


class ReviewPackageResponse(BaseModel):
    review_session_id: UUID
    thread_id: str
    finalization_run_id: UUID
    tender_version_id: UUID
    status: str
    package: dict[str, Any]
    corrected_profile: dict[str, Any] | None = None
    corrections: list[ReviewCorrection] = Field(default_factory=list)
    decision: str | None = None
    comment: str | None = None
    correction_count: int = 0
    reviewer_user_id: str | None = None


class ReviewDecisionResponse(BaseModel):
    review_session_id: UUID
    thread_id: str
    status: str
    workflow_status: str
    correction_count: int
    completed: bool
