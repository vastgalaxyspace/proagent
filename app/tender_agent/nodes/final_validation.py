from __future__ import annotations

from langgraph.runtime import Runtime

from app.tender_agent.context import (
    TenderRuntimeContext,
)
from app.tender_agent.schemas.finalization import (
    CoverageAuditResult,
    TenderProfilePayload,
)
from app.tender_agent.state import TenderAgentState


def final_validation_node(
    state: TenderAgentState,
    runtime: Runtime[TenderRuntimeContext],
) -> TenderAgentState:
    service = runtime.context.get(
        "validation_service"
    )

    if service is None:
        return {
            "final_validation_completed": False,
            "workflow_status": "failed",
            "current_node": "final_validation",
            "next_action": "mark_failed",
            "errors": [
                "Final validation service is unavailable."
            ],
        }

    try:
        profile = TenderProfilePayload.model_validate(
            state["tender_profile"]
        )
        coverage = CoverageAuditResult.model_validate(
            state["coverage_audit"]
        )

        validation = service.validate(
            profile=profile,
            coverage=coverage,
        )

    except Exception as exc:
        return {
            "final_validation_completed": False,
            "workflow_status": "failed",
            "current_node": "final_validation",
            "next_action": "mark_failed",
            "errors": [
                f"Final validation failed: {exc}"
            ],
        }

    return {
        "final_validation_completed": True,
        "final_validation_status": (
            validation.status
        ),
        "ready_for_review": (
            validation.ready_for_review
        ),
        "review_reasons": (
            validation.review_reasons
        ),
        "final_validation": (
            validation.model_dump(mode="json")
        ),
        "workflow_status": "finally_validated",
        "current_node": "final_validation",
        "next_action": "persistence",
        "warnings": (
            validation.review_reasons
            if validation.ready_for_review
            else []
        ),
        "errors": (
            [validation.summary]
            if not validation.ready_for_review
            else []
        ),
    }
