from __future__ import annotations

from uuid import UUID

from langgraph.runtime import Runtime

from app.tender_agent.context import TenderRuntimeContext
from app.tender_agent.repositories.authority_repository import (
    AuthorityRepository,
)
from app.tender_agent.state import TenderAgentState


def base_tender_node(
    state: TenderAgentState,
    runtime: Runtime[TenderRuntimeContext],
) -> TenderAgentState:
    tenant_id = runtime.context["tenant_id"]
    session_factory = runtime.context["session_factory"]
    base_tender_service = runtime.context[
        "base_tender_service"
    ]

    tender_version_id = UUID(
        state["tender_version_id"]
    )

    with session_factory() as session:
        repository = AuthorityRepository(session)

        candidates = repository.list_candidates(
            tender_version_id=tender_version_id,
            tenant_id=tenant_id,
        )

        try:
            selection = (
                base_tender_service.select_base_tender(
                    candidates
                )
            )

            plan = repository.save_base_selection(
                tender_version_id=tender_version_id,
                selection=selection,
            )

            session.commit()

        except Exception as exc:
            session.rollback()

            return {
                "base_selection_completed": False,
                "workflow_status": "failed",
                "current_node": "base_tender",
                "next_action": "mark_failed",
                "errors": [
                    f"Base-tender selection failed: {exc}"
                ],
            }

    warnings = []

    if selection.needs_review:
        warnings.append(
            "Base-tender selection requires human review."
        )

    return {
        "base_selection_completed": True,
        "source_plan_id": str(plan.id),
        "primary_base_logical_document_id": str(
            selection.primary_logical_document_id
        ),
        "base_supporting_logical_document_ids": [
            str(logical_document_id)
            for logical_document_id
            in selection.supporting_logical_document_ids
        ],
        "authoritative_logical_document_ids": [
            str(logical_document_id)
            for logical_document_id
            in selection.authoritative_logical_document_ids
        ],
        "excluded_reference_logical_document_ids": [
            str(logical_document_id)
            for logical_document_id
            in selection.excluded_reference_logical_document_ids
        ],
        "base_selection_confidence": (
            selection.confidence
        ),
        "base_selection_needs_review": (
            selection.needs_review
        ),
        "workflow_status": "base_selected",
        "current_node": "base_tender",
        "next_action": "amendments",
        "warnings": warnings,
    }
