from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from uuid import UUID

from langgraph.runtime import Runtime

from app.tender_agent.context import TenderRuntimeContext
from app.tender_agent.domain.statuses import (
    DocumentExtractionStatus,
)
from app.tender_agent.repositories.document_repository import (
    DocumentRepository,
)
from app.tender_agent.state import TenderAgentState


def quality_assessment_node(
    state: TenderAgentState,
    runtime: Runtime[TenderRuntimeContext],
) -> TenderAgentState:
    tenant_id = runtime.context["tenant_id"]
    session_factory = runtime.context["session_factory"]
    quality_service = runtime.context["quality_service"]

    document_ids = [
        UUID(document_id)
        for document_id in state.get("document_ids", [])
    ]

    passed_page_ids: list[str] = []
    ocr_page_ids: list[str] = []
    warnings: list[str] = []
    assessed_count = 0

    with session_factory() as session:
        repository = DocumentRepository(session)

        rows = repository.list_pages_for_documents(
            document_ids=document_ids,
            tenant_id=tenant_id,
        )

        pages_by_document = defaultdict(list)

        for page, document in rows:
            pages_by_document[document.id].append(
                (page, document)
            )

        for document_rows in pages_by_document.values():
            quality_inputs = [
                (
                    page.id,
                    page.page_number,
                    page.native_text,
                )
                for page, _document in document_rows
            ]

            results = {
                result.page_id: result
                for result in quality_service.assess_pages(
                    quality_inputs
                )
            }

            document_requires_ocr = False

            for page, document in document_rows:
                if page.ocr_status == "succeeded":
                    assessed_count += 1
                    passed_page_ids.append(str(page.id))
                    continue

                result = results[page.id]

                ocr_eligible = (
                    Path(page.source_name).suffix.lower()
                    == ".pdf"
                )

                requires_ocr = bool(
                    result.requires_ocr
                    and ocr_eligible
                )

                repository.save_page_quality(
                    page=page,
                    score=result.score,
                    metrics=result.metrics,
                    requires_ocr=requires_ocr,
                    warning=result.warning,
                )

                assessed_count += 1

                if requires_ocr:
                    document_requires_ocr = True
                    ocr_page_ids.append(str(page.id))
                else:
                    passed_page_ids.append(str(page.id))

                    if (
                        result.requires_ocr
                        and not ocr_eligible
                    ):
                        warnings.append(
                            f"{page.source_name}: page quality "
                            "is weak, but the source is not a PDF."
                        )

            if document_requires_ocr:
                document = document_rows[0][1]
                document.extraction_status = (
                    DocumentExtractionStatus.NEEDS_OCR.value
                )

        session.commit()

    return {
        "quality_assessment_completed": True,
        "quality_page_count": assessed_count,
        "quality_passed_page_ids": passed_page_ids,
        "ocr_required_page_ids": ocr_page_ids,
        "skipped_nodes": (
            []
            if ocr_page_ids
            else ["ocr_recovery"]
        ),
        "workflow_status": "quality_assessed",
        "current_node": "quality_assessment",
        "next_action": (
            "ocr_recovery"
            if ocr_page_ids
            else "classification"
        ),
        "warnings": warnings,
    }
