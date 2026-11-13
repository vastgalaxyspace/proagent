from __future__ import annotations

from uuid import UUID

from langgraph.runtime import Runtime

from app.tender_agent.context import TenderRuntimeContext
from app.tender_agent.domain.statuses import (
    DocumentExtractionStatus,
)
from app.tender_agent.repositories.document_repository import (
    DocumentRepository,
)
from app.tender_agent.services.document_loader import (
    DocumentLoader,
)
from app.tender_agent.state import TenderAgentState


def native_extraction_node(
    state: TenderAgentState,
    runtime: Runtime[TenderRuntimeContext],
) -> TenderAgentState:
    tenant_id = runtime.context["tenant_id"]
    session_factory = runtime.context["session_factory"]
    storage = runtime.context["object_storage"]
    parser = runtime.context["native_parser"]

    loader = DocumentLoader(
        storage=storage,
        parser=parser,
    )

    extracted_ids: list[str] = []
    ocr_ids: list[str] = []
    empty_ids: list[str] = []
    failed_ids: list[str] = []

    warnings: list[str] = []
    page_count = 0
    character_count = 0

    for document_id_text in state.get("document_ids", []):
        try:
            document_id = UUID(document_id_text)
        except ValueError:
            failed_ids.append(document_id_text)
            warnings.append(
                f"Invalid document ID: {document_id_text}"
            )
            continue

        with session_factory() as session:
            repository = DocumentRepository(session)

            document = repository.get_for_tenant(
                document_id=document_id,
                tenant_id=tenant_id,
            )

            if document is None:
                failed_ids.append(document_id_text)
                warnings.append(
                    f"Document was not found: {document_id_text}"
                )
                continue

            existing_extraction = repository.get_extraction(
                document_id=document.id,
            )

            if (
                existing_extraction is not None
                and document.extraction_status
                in {
                    DocumentExtractionStatus.EXTRACTED.value,
                    DocumentExtractionStatus.NEEDS_OCR.value,
                    DocumentExtractionStatus.EMPTY.value,
                }
            ):
                page_count += existing_extraction.page_count
                character_count += (
                    existing_extraction.character_count
                )

                if (
                    document.extraction_status
                    == DocumentExtractionStatus.EXTRACTED.value
                ):
                    extracted_ids.append(str(document.id))

                elif (
                    document.extraction_status
                    == DocumentExtractionStatus.NEEDS_OCR.value
                ):
                    ocr_ids.append(str(document.id))

                else:
                    empty_ids.append(str(document.id))

                continue

            repository.mark_processing(document)
            session.commit()

            try:
                if not document.object_key:
                    raise ValueError(
                        "Document has no object-storage key."
                    )

                result = loader.extract(
                    document_id=str(document.id),
                    file_name=document.file_name,
                    object_key=document.object_key,
                )

                repository.save_extraction(
                    document=document,
                    result=result,
                )

                session.commit()

                page_count += len(result.pages)
                character_count += len(result.text)

                warnings.extend(
                    f"{document.file_name}: {warning}"
                    for warning in result.warnings
                )

                if result.status == "needs_ocr":
                    ocr_ids.append(str(document.id))

                elif result.status == "empty":
                    empty_ids.append(str(document.id))

                else:
                    extracted_ids.append(str(document.id))

            except Exception as exc:
                session.rollback()

                document = repository.get_for_tenant(
                    document_id=document_id,
                    tenant_id=tenant_id,
                )

                if document is not None:
                    repository.mark_extraction_failed(
                        document=document,
                        error=str(exc),
                    )
                    session.commit()

                failed_ids.append(str(document_id))
                warnings.append(
                    f"{document.file_name}: native extraction "
                    f"failed: {exc}"
                )

    usable_document_count = (
        len(extracted_ids) + len(ocr_ids)
    )

    if usable_document_count == 0:
        return {
            "native_extraction_completed": False,
            "extracted_document_ids": extracted_ids,
            "ocr_document_ids": ocr_ids,
            "empty_document_ids": empty_ids,
            "failed_document_ids": failed_ids,
            "extracted_page_count": page_count,
            "extracted_character_count": character_count,
            "workflow_status": "failed",
            "current_node": "native_extraction",
            "next_action": "mark_failed",
            "warnings": warnings,
            "errors": [
                "No tender document produced usable native text."
            ],
        }

    return {
        "native_extraction_completed": True,
        "extracted_document_ids": extracted_ids,
        "ocr_document_ids": ocr_ids,
        "empty_document_ids": empty_ids,
        "failed_document_ids": failed_ids,
        "extracted_page_count": page_count,
        "extracted_character_count": character_count,
        "workflow_status": "native_extracted",
        "current_node": "native_extraction",
        "next_action": "quality_assessment",
        "warnings": warnings,
    }
