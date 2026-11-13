from __future__ import annotations

from collections import Counter, defaultdict
from uuid import UUID

from langgraph.runtime import Runtime

from app.tender_agent.context import TenderRuntimeContext
from app.tender_agent.repositories.structure_repository import (
    StructureRepository,
)
from app.tender_agent.state import TenderAgentState


def structure_node(
    state: TenderAgentState,
    runtime: Runtime[TenderRuntimeContext],
) -> TenderAgentState:
    tenant_id = runtime.context["tenant_id"]
    session_factory = runtime.context["session_factory"]
    structure_service = runtime.context[
        "structure_service"
    ]

    document_ids = [
        UUID(document_id)
        for document_id in state.get("document_ids", [])
    ]

    logical_document_ids: list[str] = []
    review_logical_document_ids: list[str] = []
    type_counts: Counter[str] = Counter()
    warnings: list[str] = []

    structured_page_count = 0

    with session_factory() as session:
        repository = StructureRepository(session)

        classified_pages = repository.list_classified_pages(
            document_ids=document_ids,
            tenant_id=tenant_id,
        )

        pages_by_document = defaultdict(list)

        for page in classified_pages:
            pages_by_document[page.document_id].append(page)

        for document_id in document_ids:
            pages = pages_by_document.get(
                document_id,
                [],
            )

            if not pages:
                warnings.append(
                    "No classified pages were available for "
                    f"document {document_id}."
                )
                continue

            drafts = structure_service.reconstruct(pages)

            persisted_documents = (
                repository.replace_document_structure(
                    document_id=document_id,
                    drafts=drafts,
                )
            )

            for draft, persisted in zip(
                drafts,
                persisted_documents,
                strict=True,
            ):
                logical_document_ids.append(
                    str(persisted.id)
                )

                type_counts[draft.document_type] += 1
                structured_page_count += draft.page_count

                if draft.needs_review:
                    review_logical_document_ids.append(
                        str(persisted.id)
                    )

        session.commit()

    if not logical_document_ids:
        return {
            "structure_completed": False,
            "logical_document_ids": [],
            "logical_document_count": 0,
            "structured_page_count": 0,
            "structure_review_logical_document_ids": [],
            "logical_document_type_counts": {},
            "workflow_status": "failed",
            "current_node": "structure",
            "next_action": "mark_failed",
            "warnings": warnings,
            "errors": [
                "No logical tender documents could be "
                "reconstructed."
            ],
        }

    if review_logical_document_ids:
        warnings.append(
            f"{len(review_logical_document_ids)} logical "
            "document(s) require structure review."
        )

    return {
        "structure_completed": True,
        "logical_document_ids": logical_document_ids,
        "logical_document_count": len(
            logical_document_ids
        ),
        "structured_page_count": structured_page_count,
        "structure_review_logical_document_ids": (
            review_logical_document_ids
        ),
        "logical_document_type_counts": dict(type_counts),
        "workflow_status": "structured",
        "current_node": "structure",
        "next_action": "base_tender",
        "warnings": warnings,
    }
