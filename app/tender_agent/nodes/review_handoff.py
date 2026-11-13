from __future__ import annotations

from uuid import UUID

from langgraph.runtime import Runtime
from langgraph.types import interrupt

from app.tender_agent.context import TenderRuntimeContext
from app.tender_agent.repositories.audit_repository import AuditRepository
from app.tender_agent.repositories.review_repository import ReviewRepository
from app.tender_agent.schemas.review import ReviewResumeCommand
from app.tender_agent.state import TenderAgentState


def review_handoff_node(
    state: TenderAgentState,
    runtime: Runtime[TenderRuntimeContext],
) -> TenderAgentState:
    context = runtime.context
    finalization_run_id = state.get("finalization_run_id")
    if not finalization_run_id or not state.get("ready_for_review"):
        return {
            "workflow_status": "failed",
            "current_node": "review_handoff",
            "next_action": None,
            "errors": ["A review-ready finalization snapshot is required."],
        }

    with context["session_factory"]() as session:
        repository = ReviewRepository(session)
        finalization = repository.get_finalization(
            finalization_run_id=UUID(finalization_run_id),
            tenant_id=context["tenant_id"],
        )
        if finalization is None:
            raise ValueError("Finalization snapshot was not found for tenant.")

        issues = repository.list_issues(finalization_run_id=finalization.id)
        package = context["handoff_service"].build_package(
            finalization=finalization,
            issues=issues,
        )
        review = repository.ensure_session(
            finalization=finalization,
            tenant_id=context["tenant_id"],
            thread_id=context["thread_id"],
            package=package,
        )
        review_id = review.id
        session.commit()

    response = interrupt(
        {
            "review_session_id": str(review_id),
            "thread_id": context["thread_id"],
            "status": "awaiting_review",
            "package": package,
        }
    )
    command = ReviewResumeCommand.model_validate(response)
    corrected_profile = context["handoff_service"].apply_corrections(
        profile=package["profile"],
        corrections=command.corrections,
    )

    with context["session_factory"]() as session:
        repository = ReviewRepository(session)
        review = repository.get_by_thread(
            thread_id=context["thread_id"],
            tenant_id=context["tenant_id"],
        )
        if review is None:
            raise ValueError("Review session was not found.")
        repository.record_decision(
            review=review,
            command=command,
            corrected_profile=corrected_profile,
        )
        AuditRepository(session).record(
            tenant_id=context["tenant_id"],
            actor_user_id=command.reviewer_user_id,
            event_type=f"tender.review.{command.decision}",
            entity_type="tender_review_session",
            entity_id=str(review.id),
            after={
                "decision": command.decision,
                "comment": command.comment,
                "correction_count": len(command.corrections),
            },
        )
        session.commit()

    return {
        "workflow_status": command.decision,
        "current_node": "review_handoff",
        "next_action": None,
        "review_handoff_completed": True,
        "review_session_id": str(review_id),
        "review_status": command.decision,
        "review_decision": command.decision,
        "review_comment": command.comment,
        "review_correction_count": len(command.corrections),
        "reviewed_by_user_id": command.reviewer_user_id,
        "tender_agent_completed": True,
    }
