from __future__ import annotations

from uuid import UUID

from langgraph.runtime import Runtime

from app.tender_agent.context import (
    TenderRuntimeContext,
)
from app.tender_agent.repositories.finalization_repository import (
    FinalizationRepository,
)
from app.tender_agent.state import TenderAgentState


def profile_projection_node(
    state: TenderAgentState,
    runtime: Runtime[TenderRuntimeContext],
) -> TenderAgentState:
    session_factory = runtime.context[
        "session_factory"
    ]
    tenant_id = runtime.context["tenant_id"]

    try:
        normalization_run_id = UUID(
            state["normalization_run_id"]
        )
        requirement_run_id = UUID(
            state["requirement_run_id"]
        )

        with session_factory() as session:
            repository = FinalizationRepository(
                session
            )

            profile = repository.project_profile(
                normalization_run_id=(
                    normalization_run_id
                ),
                requirement_run_id=(
                    requirement_run_id
                ),
                tenant_id=tenant_id,
            )

    except Exception as exc:
        return {
            "profile_projection_completed": False,
            "workflow_status": "failed",
            "current_node": "profile_projection",
            "next_action": "mark_failed",
            "errors": [
                f"Profile projection failed: {exc}"
            ],
        }

    return {
        "profile_projection_completed": True,
        "projected_field_count": (
            profile.field_count
        ),
        "projected_requirement_count": (
            profile.requirement_count
        ),
        "tender_profile": profile.model_dump(
            mode="json"
        ),
        "workflow_status": "profile_projected",
        "current_node": "profile_projection",
        "next_action": "coverage_audit",
        "warnings": [],
    }