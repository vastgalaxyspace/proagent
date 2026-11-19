from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.infrastructure.database.models import (
    Tender,
    TenderFinalizationIssue,
    TenderFinalizationRun,
    TenderReviewCorrection,
    TenderReviewSession,
    TenderVersion,
)
from app.tender_agent.schemas.review import ReviewResumeCommand
from app.tender_agent.domain.statuses import TenderStatus, TenderVersionStatus


class ReviewRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_finalization(
        self,
        *,
        finalization_run_id: UUID,
        tenant_id: str,
    ) -> TenderFinalizationRun | None:
        return self.session.scalar(
            select(TenderFinalizationRun)
            .join(TenderVersion, TenderVersion.id == TenderFinalizationRun.tender_version_id)
            .join(Tender, Tender.id == TenderVersion.tender_id)
            .where(
                TenderFinalizationRun.id == finalization_run_id,
                TenderFinalizationRun.ready_for_review.is_(True),
                Tender.tenant_id == tenant_id,
            )
        )

    def list_issues(self, *, finalization_run_id: UUID) -> list[TenderFinalizationIssue]:
        return list(
            self.session.scalars(
                select(TenderFinalizationIssue)
                .where(TenderFinalizationIssue.finalization_run_id == finalization_run_id)
                .order_by(TenderFinalizationIssue.created_at, TenderFinalizationIssue.id)
            )
        )

    def ensure_session(
        self,
        *,
        finalization: TenderFinalizationRun,
        tenant_id: str,
        thread_id: str,
        package: dict[str, Any],
        reset_existing: bool = False,
    ) -> TenderReviewSession:
        existing = self.session.scalar(
            select(TenderReviewSession).where(
                TenderReviewSession.finalization_run_id == finalization.id
            )
        )
        if existing is not None:
            if existing.tenant_id != tenant_id or existing.thread_id != thread_id:
                raise ValueError("Finalization is already attached to another review run.")
            if reset_existing:
                self.session.execute(
                    delete(TenderReviewCorrection).where(
                        TenderReviewCorrection.review_session_id
                        == existing.id
                    )
                )
                existing.status = "awaiting_review"
                existing.package_json = package
                existing.original_profile_json = finalization.profile_json
                existing.corrected_profile_json = None
                existing.decision = None
                existing.comment = None
                existing.reviewer_user_id = None
                existing.correction_count = 0
                existing.reviewed_at = None
                self.session.flush()
            return existing

        review = TenderReviewSession(
            tenant_id=tenant_id,
            finalization_run_id=finalization.id,
            tender_version_id=finalization.tender_version_id,
            thread_id=thread_id,
            status="awaiting_review",
            package_json=package,
            original_profile_json=finalization.profile_json,
            correction_count=0,
        )
        self.session.add(review)
        version = self.session.get(TenderVersion, finalization.tender_version_id)
        if version is None:
            raise ValueError("Tender version was not found.")
        tender = self.session.get(Tender, version.tender_id)
        if tender is None or tender.tenant_id != tenant_id:
            raise ValueError("Tender was not found for tenant.")
        version.status = TenderVersionStatus.REVIEW_READY.value
        tender.status = TenderStatus.REVIEW_READY.value
        self.session.flush()
        return review

    def get_by_thread(
        self,
        *,
        thread_id: str,
        tenant_id: str,
    ) -> TenderReviewSession | None:
        return self.session.scalar(
            select(TenderReviewSession).where(
                TenderReviewSession.thread_id == thread_id,
                TenderReviewSession.tenant_id == tenant_id,
            )
        )

    def list_corrections(
        self,
        *,
        review_session_id: UUID,
    ) -> list[TenderReviewCorrection]:
        return list(
            self.session.scalars(
                select(TenderReviewCorrection)
                .where(
                    TenderReviewCorrection.review_session_id
                    == review_session_id
                )
                .order_by(TenderReviewCorrection.ordinal)
            )
        )

    def record_decision(
        self,
        *,
        review: TenderReviewSession,
        command: ReviewResumeCommand,
        corrected_profile: dict[str, Any],
    ) -> None:
        if review.status != "awaiting_review":
            raise ValueError("This review has already been completed.")

        for ordinal, correction in enumerate(command.corrections, start=1):
            self.session.add(
                TenderReviewCorrection(
                    review_session_id=review.id,
                    ordinal=ordinal,
                    target_type=correction.target_type,
                    target_key=correction.target_key,
                    patch_json=correction.patch,
                    reason=correction.reason,
                    applied=True,
                )
            )

        review.status = command.decision
        review.decision = command.decision
        review.comment = command.comment
        review.reviewer_user_id = command.reviewer_user_id
        review.corrected_profile_json = corrected_profile
        review.correction_count = len(command.corrections)
        review.reviewed_at = datetime.now(timezone.utc)

        finalization = self.session.get(TenderFinalizationRun, review.finalization_run_id)
        if finalization is None:
            raise ValueError("Finalization snapshot was not found.")
        if command.decision == "approved":
            finalization.profile_json = corrected_profile
            version = self.session.get(TenderVersion, review.tender_version_id)
            if version is None:
                raise ValueError("Tender version was not found.")
            tender = self.session.get(Tender, version.tender_id)
            if tender is None or tender.tenant_id != review.tenant_id:
                raise ValueError("Tender was not found for tenant.")
            version.understanding_json = corrected_profile
            version.status = TenderVersionStatus.APPROVED.value
            tender.status = TenderStatus.APPROVED.value

        self.session.flush()
