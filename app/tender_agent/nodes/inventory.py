from __future__ import annotations

from uuid import UUID

from langgraph.runtime import Runtime

from app.tender_agent.context import TenderRuntimeContext
from app.tender_agent.domain.statuses import DocumentStorageStatus
from app.tender_agent.repositories.document_repository import (
    DocumentRepository,
)
from app.tender_agent.state import TenderAgentState


def inventory_node(
    state: TenderAgentState,
    runtime: Runtime[TenderRuntimeContext],
) -> TenderAgentState:
    tenant_id = runtime.context["tenant_id"]
    session_factory = runtime.context["session_factory"]
    storage = runtime.context["object_storage"]

    errors: list[str] = []
    warnings: list[str] = []

    version_id_text = state.get("tender_version_id", "").strip()

    try:
        tender_version_id = UUID(version_id_text)
    except ValueError:
        return {
            "ingestion_verified": False,
            "workflow_status": "failed",
            "current_node": "inventory",
            "next_action": "mark_failed",
            "errors": ["Tender version ID is invalid."],
        }

    with session_factory() as session:
        document_repository = DocumentRepository(session)

        documents = document_repository.list_for_version(
            tender_version_id=tender_version_id,
            tenant_id=tenant_id,
        )

        if not documents:
            errors.append(
                "The tender version has no uploaded documents."
            )

        total_bytes = 0

        for document in documents:
            document_label = (
                f"{document.file_name} ({document.id})"
            )

            if (
                document.storage_status
                != DocumentStorageStatus.STORED.value
            ):
                errors.append(
                    f"{document_label} is not marked as stored."
                )
                continue

            if not document.object_key:
                errors.append(
                    f"{document_label} has no object-storage key."
                )
                continue

            if document.size_bytes is None:
                errors.append(
                    f"{document_label} has no recorded size."
                )
            elif document.size_bytes <= 0:
                errors.append(
                    f"{document_label} has an invalid size."
                )
            else:
                total_bytes += document.size_bytes

            if not document.sha256:
                errors.append(
                    f"{document_label} has no SHA-256 checksum."
                )

            if not storage.exists(document.object_key):
                errors.append(
                    f"{document_label} is missing from object storage."
                )

            if (
                document.content_type
                == "application/octet-stream"
            ):
                warnings.append(
                    f"{document.file_name} has a generic content type."
                )

    if errors:
        return {
            "ingestion_verified": False,
            "ingested_document_count": len(documents),
            "ingested_total_bytes": total_bytes,
            "workflow_status": "failed",
            "current_node": "inventory",
            "next_action": "mark_failed",
            "warnings": warnings,
            "errors": errors,
        }

    return {
        "document_ids": [
            str(document.id)
            for document in documents
        ],
        "ingestion_verified": True,
        "ingested_document_count": len(documents),
        "ingested_total_bytes": total_bytes,
        "workflow_status": "inventorying",
        "current_node": "inventory",
        "next_action": "preflight",
        "warnings": warnings,
    }