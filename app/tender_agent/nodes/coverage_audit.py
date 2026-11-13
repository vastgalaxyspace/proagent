from __future__ import annotations

from langgraph.runtime import Runtime

from app.tender_agent.context import (
    TenderRuntimeContext,
)
from app.tender_agent.schemas.finalization import (
    TenderProfilePayload,
)
from app.tender_agent.state import TenderAgentState


def coverage_audit_node(
    state: TenderAgentState,
    runtime: Runtime[TenderRuntimeContext],
) -> TenderAgentState:
    service = runtime.context.get(
        "coverage_service"
    )
    field_catalog = runtime.context.get(
        "field_catalog"
    )

    if service is None or field_catalog is None:
        return {
            "coverage_audit_completed": False,
            "workflow_status": "failed",
            "current_node": "coverage_audit",
            "next_action": "mark_failed",
            "errors": [
                "Coverage service or field catalog is "
                "unavailable."
            ],
        }

    try:
        profile = TenderProfilePayload.model_validate(
            state["tender_profile"]
        )

        coverage = service.audit(
            profile=profile,
            field_catalog=field_catalog,
        )

    except Exception as exc:
        return {
            "coverage_audit_completed": False,
            "workflow_status": "failed",
            "current_node": "coverage_audit",
            "next_action": "mark_failed",
            "errors": [
                f"Coverage audit failed: {exc}"
            ],
        }

    return {
        "coverage_audit_completed": True,
        "readiness_score": (
            coverage.readiness_score
        ),
        "coverage_issue_count": len(
            coverage.issues
        ),
        "coverage_warning_count": (
            coverage.warning_count
        ),
        "coverage_error_count": (
            coverage.error_count
        ),
        "coverage_fatal_count": (
            coverage.fatal_count
        ),
        "coverage_audit": coverage.model_dump(
            mode="json"
        ),
        "workflow_status": "coverage_audited",
        "current_node": "coverage_audit",
        "next_action": "final_validation",
        "warnings": [
            issue.message
            for issue in coverage.issues
            if issue.severity == "warning"
        ],
    }