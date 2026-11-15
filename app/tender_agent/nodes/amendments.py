from __future__ import annotations

from uuid import UUID

from langgraph.runtime import Runtime

from app.tender_agent.context import TenderRuntimeContext
from app.tender_agent.domain.authority import (
    BaseTenderSelection,
)
from app.tender_agent.repositories.authority_repository import (
    AuthorityRepository,
)
from app.tender_agent.state import TenderAgentState


def amendments_node(
    state: TenderAgentState,
    runtime: Runtime[TenderRuntimeContext],
) -> TenderAgentState:
    tenant_id = runtime.context["tenant_id"]
    session_factory = runtime.context["session_factory"]
    amendment_service = runtime.context[
        "amendment_service"
    ]

    tender_version_id = UUID(
        state["tender_version_id"]
    )
    source_plan_id = UUID(state["source_plan_id"])

    selection = BaseTenderSelection(
        primary_logical_document_id=UUID(
            state["primary_base_logical_document_id"]
        ),
        supporting_logical_document_ids=[
            UUID(logical_document_id)
            for logical_document_id in state.get(
                "base_supporting_logical_document_ids",
                [],
            )
        ],
        authoritative_logical_document_ids=[
            UUID(logical_document_id)
            for logical_document_id in (
                state.get(
                    "authoritative_logical_document_ids",
                    [],
                )
                or [
                    state["primary_base_logical_document_id"],
                    *state.get(
                        "base_supporting_logical_document_ids",
                        [],
                    ),
                ]
            )
        ],
        excluded_reference_logical_document_ids=[
            UUID(logical_document_id)
            for logical_document_id in state.get(
                "excluded_reference_logical_document_ids",
                [],
            )
        ],
        confidence=state.get(
            "base_selection_confidence",
            0.0,
        ),
        needs_review=state.get(
            "base_selection_needs_review",
            True,
        ),
        reason="Loaded from durable LangGraph state.",
    )

    with session_factory() as session:
        repository = AuthorityRepository(session)

        plan = repository.get_plan(
            source_plan_id=source_plan_id
        )

        if plan is None:
            return {
                "amendment_resolution_completed": False,
                "workflow_status": "failed",
                "current_node": "amendments",
                "next_action": "mark_failed",
                "errors": [
                    "Tender source plan was not found."
                ],
            }

        candidates = repository.list_candidates(
            tender_version_id=tender_version_id,
            tenant_id=tenant_id,
        )

        try:
            draft = amendment_service.build_effective_plan(
                candidates=candidates,
                selection=selection,
            )

            members = repository.finalize_plan(
                plan=plan,
                draft=draft,
            )

            session.commit()

        except Exception as exc:
            session.rollback()

            return {
                "amendment_resolution_completed": False,
                "workflow_status": "failed",
                "current_node": "amendments",
                "next_action": "mark_failed",
                "errors": [
                    f"Amendment resolution failed: {exc}"
                ],
            }

    binding_ids = [
        str(member.logical_document_id)
        for member in members
        if (
            member.binding_status == "binding"
            and member.source_role
            in {
                "corrigendum",
                "prebid_clarification",
            }
        )
    ]

    review_ids = [
        str(member.logical_document_id)
        for member in members
        if member.binding_status == "review_required"
    ]

    return {
        "amendment_resolution_completed": True,
        "effective_source_member_ids": [
            str(member.id)
            for member in members
        ],
        "effective_source_count": len(members),
        "binding_amendment_logical_document_ids": (
            binding_ids
        ),
        "review_amendment_logical_document_ids": (
            review_ids
        ),
        "effective_source_needs_review": (
            draft.needs_review
        ),
        "amendment_operation_count": len(
            draft.operations
        ),
        "validated_amendment_operation_count": sum(
            operation.validation_status == "validated"
            for operation in draft.operations
        ),
        "review_amendment_operation_count": sum(
            operation.validation_status == "review_required"
            for operation in draft.operations
        ),
        "amendment_operations": [
            {
                "logical_document_id": str(
                    operation.logical_document_id
                ),
                "page_id": str(operation.page_id),
                "operation": operation.operation,
                "target": operation.target,
                "previous_value": operation.previous_value,
                "revised_value": operation.revised_value,
                "evidence_quote": operation.evidence_quote,
                "confidence": operation.confidence,
                "validation_status": (
                    operation.validation_status
                ),
                "reason": operation.reason,
            }
            for operation in draft.operations
        ],
        "workflow_status": "amendments_resolved",
        "current_node": "amendments",
        "next_action": "retrieval",
        "warnings": draft.warnings,
    }
