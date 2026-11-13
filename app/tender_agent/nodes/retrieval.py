from __future__ import annotations

from uuid import UUID

from langgraph.runtime import Runtime

from app.tender_agent.context import TenderRuntimeContext
from app.tender_agent.repositories.retrieval_repository import (
    RetrievalRepository,
)
from app.tender_agent.state import TenderAgentState


def retrieval_node(
    state: TenderAgentState,
    runtime: Runtime[TenderRuntimeContext],
) -> TenderAgentState:
    service = runtime.context.get("retrieval_service")

    if service is None:
        return {
            "retrieval_index_completed": False,
            "workflow_status": "failed",
            "current_node": "retrieval",
            "next_action": "mark_failed",
            "errors": ["Retrieval service is unavailable."],
        }

    try:
        tender_version_id = UUID(
            state["tender_version_id"]
        )
        source_plan_id = UUID(state["source_plan_id"])
        tenant_id = runtime.context["tenant_id"]
        session_factory = runtime.context[
            "session_factory"
        ]

        with session_factory() as session:
            repository = RetrievalRepository(session)
            pages = repository.list_source_pages(
                tender_version_id=tender_version_id,
                source_plan_id=source_plan_id,
                tenant_id=tenant_id,
            )

        if not pages:
            raise ValueError(
                "No effective tender pages were available."
            )

        result = service.build_index(pages)

        if not result.chunks:
            raise ValueError(
                "No searchable retrieval chunks were built."
            )

        with session_factory() as session:
            repository = RetrievalRepository(session)
            index = repository.replace_index(
                tender_version_id=tender_version_id,
                source_plan_id=source_plan_id,
                result=result,
                embedding_provider=(
                    service.embedding_provider_name
                ),
                embedding_model=service.embedding_model,
                embedding_dimensions=(
                    service.embedding_dimensions
                ),
                reranker_provider=(
                    service.reranker_provider_name
                ),
                reranker_model=service.reranker_model,
                chunk_characters=(
                    service.limits.chunk_characters
                ),
                chunk_overlap_characters=(
                    service.limits
                    .chunk_overlap_characters
                ),
            )
            session.commit()

    except Exception as exc:
        return {
            "retrieval_index_completed": False,
            "workflow_status": "failed",
            "current_node": "retrieval",
            "next_action": "mark_failed",
            "errors": [f"Retrieval indexing failed: {exc}"],
        }

    return {
        "retrieval_index_completed": True,
        "retrieval_index_id": str(index.id),
        "retrieval_chunk_count": len(result.chunks),
        "retrieval_indexed_page_count": (
            result.indexed_page_count
        ),
        "retrieval_skipped_page_count": (
            result.skipped_page_count
        ),
        "retrieval_embedding_provider": (
            service.embedding_provider_name
        ),
        "retrieval_embedding_model": service.embedding_model,
        "retrieval_embedding_dimensions": (
            service.embedding_dimensions
        ),
        "retrieval_reranker_provider": (
            service.reranker_provider_name
        ),
        "retrieval_reranker_model": service.reranker_model,
        "workflow_status": "retrieval_indexed",
        "current_node": "retrieval",
        "next_action": "field_understanding",
    }
