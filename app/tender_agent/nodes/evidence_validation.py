from __future__ import annotations

from uuid import UUID

from langgraph.runtime import Runtime

from app.tender_agent.context import (
    TenderRuntimeContext,
)
from app.tender_agent.repositories.requirement_repository import (
    RequirementRepository,
)
from app.tender_agent.repositories.retrieval_repository import (
    RetrievalRepository,
)
from app.tender_agent.state import TenderAgentState


def evidence_validation_node(
    state: TenderAgentState,
    runtime: Runtime[TenderRuntimeContext],
) -> TenderAgentState:
    service = runtime.context.get(
        "evidence_service"
    )

    if service is None:
        return {
            "requirement_evidence_validated": False,
            "workflow_status": "failed",
            "current_node": "evidence_validation",
            "next_action": "mark_failed",
            "errors": [
                "Evidence validation service is "
                "unavailable."
            ],
        }

    tenant_id = runtime.context["tenant_id"]
    session_factory = runtime.context[
        "session_factory"
    ]

    try:
        requirement_run_id = UUID(
            state["requirement_run_id"]
        )
        retrieval_index_id = UUID(
            state["retrieval_index_id"]
        )

        with session_factory() as session:
            requirement_repository = (
                RequirementRepository(session)
            )
            retrieval_repository = (
                RetrievalRepository(session)
            )

            run, requirements = (
                requirement_repository
                .load_for_validation(
                    requirement_run_id=(
                        requirement_run_id
                    ),
                    tenant_id=tenant_id,
                )
            )

            chunks = retrieval_repository.list_chunks(
                retrieval_index_id=retrieval_index_id,
                tenant_id=tenant_id,
            )

        result = service.validate(
            requirements=requirements,
            chunks=chunks,
        )

        with session_factory() as session:
            repository = RequirementRepository(
                session
            )

            stored_run, _ = (
                repository.load_for_validation(
                    requirement_run_id=(
                        requirement_run_id
                    ),
                    tenant_id=tenant_id,
                )
            )

            repository.apply_validation(
                run=stored_run,
                result=result,
            )

            session.commit()

    except Exception as exc:
        return {
            "requirement_evidence_validated": False,
            "workflow_status": "failed",
            "current_node": "evidence_validation",
            "next_action": "mark_failed",
            "errors": [
                f"Requirement evidence validation "
                f"failed: {exc}"
            ],
        }

    return {
        "requirement_evidence_validated": True,
        "validated_requirement_count": (
            result.validated_count
        ),
        "review_requirement_count": (
            result.review_count
        ),
        "invalid_requirement_count": (
            result.invalid_count
        ),
        "requirement_review_codes": (
            result.review_requirement_codes
        ),
        "invalid_requirement_codes": (
            result.invalid_requirement_codes
        ),
        "workflow_status": "evidence_validated",
        "current_node": "evidence_validation",
        "next_action": "mark_ready",
        "warnings": result.warnings,
    }