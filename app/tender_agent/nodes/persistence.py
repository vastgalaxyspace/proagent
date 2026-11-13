from __future__ import annotations

from langgraph.runtime import Runtime

from app.tender_agent.context import (
    TenderRuntimeContext,
)
from app.tender_agent.repositories.finalization_repository import (
    FinalizationRepository,
)
from app.tender_agent.schemas.finalization import (
    CoverageAuditResult,
    FinalValidationResult,
    TenderProfilePayload,
)
from app.tender_agent.state import TenderAgentState


def persistence_node(
    state: TenderAgentState,
    runtime: Runtime[TenderRuntimeContext],
) -> TenderAgentState:
    session_factory = runtime.context[
        "session_factory"
    ]
    tenant_id = runtime.context["tenant_id"]

    try:
        profile = TenderProfilePayload.model_validate(
            state["tender_profile"]
        )
        coverage = CoverageAuditResult.model_validate(
            state["coverage_audit"]
        )
        validation = FinalValidationResult.model_validate(
            state["final_validation"]
        )

        with session_factory() as session:
            repository = FinalizationRepository(
                session
            )

            run = repository.replace_finalization(
                tenant_id=tenant_id,
                profile=profile,
                coverage=coverage,
                validation=validation,
            )

            session.commit()

    except Exception as exc:
        return {
            "final_persistence_completed": False,
            "workflow_status": "failed",
            "current_node": "persistence",
            "next_action": "mark_failed",
            "errors": [
                f"Final persistence failed: {exc}"
            ],
        }

    return {
        "final_persistence_completed": True,
        "finalization_run_id": str(run.id),
        "workflow_status": "persisted",
        "current_node": "persistence",
        "next_action": "review_handoff",
        "warnings": [],
    }
