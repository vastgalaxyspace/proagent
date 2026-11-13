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


def requirement_matrix_node(
    state: TenderAgentState,
    runtime: Runtime[TenderRuntimeContext],
) -> TenderAgentState:
    service = runtime.context.get(
        "requirement_service"
    )
    ai_providers = runtime.context.get(
        "ai_providers"
    )

    if service is None or ai_providers is None:
        return {
            "requirement_extraction_completed": False,
            "workflow_status": "failed",
            "current_node": "requirement_matrix",
            "next_action": "mark_failed",
            "errors": [
                "Requirement extraction AI service is "
                "unavailable."
            ],
        }

    tenant_id = runtime.context["tenant_id"]
    session_factory = runtime.context[
        "session_factory"
    ]

    try:
        tender_version_id = UUID(
            state["tender_version_id"]
        )
        normalization_run_id = UUID(
            state["normalization_run_id"]
        )
        retrieval_index_id = UUID(
            state["retrieval_index_id"]
        )

        with session_factory() as session:
            retrieval_repository = (
                RetrievalRepository(session)
            )

            chunks = retrieval_repository.list_chunks(
                retrieval_index_id=retrieval_index_id,
                tenant_id=tenant_id,
            )

        result = service.build(chunks=chunks)

        with session_factory() as session:
            repository = RequirementRepository(
                session
            )

            run = repository.replace_requirements(
                tender_version_id=tender_version_id,
                normalization_run_id=(
                    normalization_run_id
                ),
                retrieval_index_id=(
                    retrieval_index_id
                ),
                tenant_id=tenant_id,
                catalog_schema_id=(
                    service.catalog.schema_id
                ),
                catalog_schema_version=(
                    service.catalog.schema_version
                ),
                llm_provider=ai_providers.llm.name,
                llm_model=ai_providers.llm.model,
                result=result,
            )

            session.commit()

    except Exception as exc:
        return {
            "requirement_extraction_completed": False,
            "workflow_status": "failed",
            "current_node": "requirement_matrix",
            "next_action": "mark_failed",
            "errors": [
                f"Requirement extraction failed: {exc}"
            ],
        }

    return {
        "requirement_extraction_completed": True,
        "requirement_run_id": str(run.id),
        "requirement_count": (
            result.requirement_count
        ),
        "mandatory_requirement_count": (
            result.mandatory_count
        ),
        "conditional_requirement_count": (
            result.conditional_count
        ),
        "informational_requirement_count": (
            result.informational_count
        ),
        "requirement_review_codes": (
            result.review_requirement_codes
        ),
        "workflow_status": "requirements_extracted",
        "current_node": "requirement_matrix",
        "next_action": "evidence_validation",
        "warnings": result.warnings,
    }