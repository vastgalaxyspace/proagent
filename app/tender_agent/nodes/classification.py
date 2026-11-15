from __future__ import annotations

from collections import Counter, defaultdict
from uuid import UUID

from langgraph.runtime import Runtime

from app.tender_agent.context import TenderRuntimeContext
from app.tender_agent.repositories.classification_repository import (
    ClassificationRepository,
)
from app.tender_agent.repositories.document_repository import (
    DocumentRepository,
)
from app.tender_agent.state import TenderAgentState


def classification_node(
    state: TenderAgentState,
    runtime: Runtime[TenderRuntimeContext],
) -> TenderAgentState:
    tenant_id = runtime.context["tenant_id"]
    session_factory = runtime.context["session_factory"]
    classification_service = runtime.context[
        "classification_service"
    ]

    document_ids = [
        UUID(document_id)
        for document_id in state.get("document_ids", [])
    ]

    classified_document_ids: list[str] = []
    review_page_ids: list[str] = []
    post_base_document_ids: list[str] = []
    warnings: list[str] = []
    type_counts: Counter[str] = Counter()
    classified_page_count = 0

    with session_factory() as session:
        document_repository = DocumentRepository(session)
        classification_repository = (
            ClassificationRepository(session)
        )

        rows = (
            document_repository.list_pages_for_documents(
                document_ids=document_ids,
                tenant_id=tenant_id,
            )
        )

        pages_by_document = defaultdict(list)

        for page, document in rows:
            pages_by_document[document.id].append(
                (page, document)
            )

        for document_id in document_ids:
            document_rows = pages_by_document.get(
                document_id,
                [],
            )

            if not document_rows:
                warnings.append(
                    "No extracted pages were available for "
                    f"document {document_id}."
                )
                continue

            page_decisions = []
            pages_by_source = defaultdict(list)

            for page, _document in document_rows:
                pages_by_source[page.source_name].append(page)

            for source_name, source_pages in pages_by_source.items():
                ordered_pages = sorted(
                    source_pages,
                    key=lambda page: (
                        page.source_page_number,
                        page.page_number,
                    ),
                )
                source_text = "\n\n".join(
                    page.extracted_text
                    for page in ordered_pages
                    if page.extracted_text
                )
                inherited = classification_service.classify_source(
                    source_name=source_name,
                    text=source_text,
                )

                for page in ordered_pages:
                    decision = classification_service.classify_page(
                        page_id=page.id,
                        page_number=page.source_page_number,
                        source_name=page.source_name,
                        text=page.extracted_text,
                        inherited=inherited,
                    )

                    if (
                        decision.classification_method
                        == "deterministic_heading"
                    ):
                        inherited = (
                            classification_service
                            .source_from_boundary(decision)
                        )

                    page_decisions.append(decision)
                    type_counts[decision.document_type] += 1
                    classified_page_count += 1

                    if (
                        decision.document_type == "unknown"
                        or decision.confidence
                        < classification_service
                        .limits.minimum_confidence
                    ):
                        review_page_ids.append(str(page.id))

            aggregate = (
                classification_service.summarize_document(
                    document_id=document_id,
                    decisions=page_decisions,
                )
            )

            classification_repository.save_document_classification(
                aggregate=aggregate,
                page_decisions=page_decisions,
            )

            classified_document_ids.append(
                str(document_id)
            )

            if any(
                decision.document_type
                in {
                    "corrigendum",
                    "prebid_clarification",
                }
                for decision in page_decisions
            ):
                post_base_document_ids.append(
                    str(document_id)
                )

        session.commit()

    if not classified_document_ids:
        return {
            "classification_completed": False,
            "classified_document_ids": [],
            "classified_page_count": 0,
            "classification_review_page_ids": [],
            "document_type_counts": {},
            "post_base_document_ids": [],
            "workflow_status": "failed",
            "current_node": "classification",
            "next_action": "mark_failed",
            "warnings": warnings,
            "errors": [
                "No extracted tender page could be classified."
            ],
        }

    if review_page_ids:
        warnings.append(
            f"{len(review_page_ids)} page(s) require "
            "classification review."
        )

    return {
        "classification_completed": True,
        "classified_document_ids": (
            classified_document_ids
        ),
        "classified_page_count": classified_page_count,
        "classification_review_page_ids": (
            review_page_ids
        ),
        "document_type_counts": dict(type_counts),
        "post_base_document_ids": (
            post_base_document_ids
        ),
        "workflow_status": "classified",
        "current_node": "classification",
        "next_action": "structure",
        "warnings": warnings,
    }
