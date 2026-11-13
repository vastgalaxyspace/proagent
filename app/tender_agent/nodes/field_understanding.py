from __future__ import annotations

from uuid import UUID

from langgraph.runtime import Runtime

from app.tender_agent.context import (
    TenderRuntimeContext,
)
from app.tender_agent.repositories.retrieval_repository import (
    RetrievalRepository,
)
from app.tender_agent.repositories.understanding_repository import (
    UnderstandingRepository,
)
from app.tender_agent.state import TenderAgentState


def field_understanding_node(
    state: TenderAgentState,
    runtime: Runtime[TenderRuntimeContext],
) -> TenderAgentState:
    tenant_id = runtime.context["tenant_id"]
    session_factory = runtime.context[
        "session_factory"
    ]

    service = runtime.context.get(
        "understanding_service"
    )
    catalog = runtime.context.get(
        "field_catalog"
    )
    ai_providers = runtime.context.get(
        "ai_providers"
    )

    if (
        service is None
        or catalog is None
        or ai_providers is None
    ):
        return {
            "field_understanding_completed": False,
            "workflow_status": "failed",
            "current_node": "field_understanding",
            "next_action": "mark_failed",
            "errors": [
                "Field-understanding AI services are "
                "unavailable."
            ],
        }

    tender_version_id = UUID(
        state["tender_version_id"]
    )
    retrieval_index_id = UUID(
        state["retrieval_index_id"]
    )

    try:
        with session_factory() as session:
            retrieval_repository = (
                RetrievalRepository(session)
            )

            chunks = retrieval_repository.list_chunks(
                retrieval_index_id=retrieval_index_id,
                tenant_id=tenant_id,
            )

        result = service.understand(
            catalog=catalog,
            chunks=chunks,
        )

        with session_factory() as session:
            repository = UnderstandingRepository(
                session
            )

            run = repository.replace_understanding(
                tender_version_id=tender_version_id,
                retrieval_index_id=retrieval_index_id,
                tenant_id=tenant_id,
                catalog=catalog,
                result=result,
                llm_provider=ai_providers.llm.name,
                llm_model=ai_providers.llm.model,
            )

            session.commit()

    except Exception as exc:
        return {
            "field_understanding_completed": False,
            "workflow_status": "failed",
            "current_node": "field_understanding",
            "next_action": "mark_failed",
            "errors": [
                f"Field understanding failed: {exc}"
            ],
        }

    return {
        "field_understanding_completed": True,
        "field_understanding_run_id": str(run.id),
        "configured_field_count": (
            result.configured_count
        ),
        "found_field_count": result.found_count,
        "not_found_field_count": (
            result.not_found_count
        ),
        "ambiguous_field_count": (
            result.ambiguous_count
        ),
        "field_error_count": result.error_count,
        "field_review_keys": (
            result.review_field_keys
        ),
        "workflow_status": "fields_understood",
        "current_node": "field_understanding",
        "next_action": "mark_ready",
        "warnings": result.warnings,
    }