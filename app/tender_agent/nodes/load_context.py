from __future__ import annotations

from uuid import UUID

from langgraph.runtime import Runtime

from app.tender_agent.context import TenderRuntimeContext
from app.tender_agent.repositories.document_repository import (
    DocumentRepository,
)
from app.tender_agent.repositories.operation_repository import (
    OperationRepository,
)
from app.tender_agent.repositories.tender_repository import TenderRepository
from app.tender_agent.state import TenderAgentState


def load_context_node(
    state: TenderAgentState,
    runtime: Runtime[TenderRuntimeContext],
) -> TenderAgentState:
    tenant_id = runtime.context["tenant_id"].strip()
    user_id = runtime.context["user_id"].strip()
    session_factory = runtime.context["session_factory"]

    errors: list[str] = []

    tender_id_text = state.get("tender_id", "").strip()
    operation_id_text = state.get("operation_id", "").strip()

    try:
        tender_id = UUID(tender_id_text)
    except ValueError:
        errors.append("Tender ID is invalid.")
        tender_id = None

    try:
        operation_id = UUID(operation_id_text)
    except ValueError:
        errors.append("Operation ID is invalid.")
        operation_id = None

    if errors:
        return {
            "owner_tenant_id": tenant_id,
            "started_by_user_id": user_id,
            "workflow_status": "failed",
            "current_node": "load_context",
            "next_action": "mark_failed",
            "errors": errors,
        }

    with session_factory() as session:
        tender_repository = TenderRepository(session)
        document_repository = DocumentRepository(session)
        operation_repository = OperationRepository(session)

        tender = tender_repository.get_tender_for_tenant(
            tender_id=tender_id,
            tenant_id=tenant_id,
        )

        operation = operation_repository.get_for_tenant(
            operation_id=operation_id,
            tenant_id=tenant_id,
        )

        if tender is None:
            errors.append("Tender was not found.")

        if operation is None:
            errors.append("Tender-understanding operation was not found.")

        if errors:
            return {
                "owner_tenant_id": tenant_id,
                "started_by_user_id": user_id,
                "workflow_status": "failed",
                "current_node": "load_context",
                "next_action": "mark_failed",
                "errors": errors,
            }

        tender_version = tender_repository.get_version_for_tenant(
            version_id=operation.tender_version_id,
            tenant_id=tenant_id,
        )

        if tender_version is None:
            errors.append("Tender version was not found.")
        elif tender_version.tender_id != tender.id:
            errors.append(
                "The operation belongs to a different tender version."
            )

        if errors:
            return {
                "owner_tenant_id": tenant_id,
                "started_by_user_id": user_id,
                "workflow_status": "failed",
                "current_node": "load_context",
                "next_action": "mark_failed",
                "errors": errors,
            }

        documents = document_repository.list_for_version(
            tender_version_id=tender_version.id,
            tenant_id=tenant_id,
        )

        return {
             "tender_version_id": str(tender_version.id),
    "document_ids": [
        str(document.id)
        for document in documents
    ],
    "owner_tenant_id": tenant_id,
    "started_by_user_id": user_id,
    "workflow_status": "loading",
    "current_node": "load_context",
    "next_action": "inventory",
        }