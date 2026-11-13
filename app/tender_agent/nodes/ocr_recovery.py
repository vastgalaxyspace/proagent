from __future__ import annotations

from uuid import UUID

from langgraph.runtime import Runtime

from app.tender_agent.context import TenderRuntimeContext
from app.tender_agent.repositories.document_repository import (
    DocumentRepository,
)
from app.tender_agent.services.ocr_service import (
    OCRRecoveryService,
)
from app.tender_agent.state import TenderAgentState


def ocr_recovery_node(
    state: TenderAgentState,
    runtime: Runtime[TenderRuntimeContext],
) -> TenderAgentState:
    tenant_id = runtime.context["tenant_id"]
    session_factory = runtime.context["session_factory"]
    storage = runtime.context["object_storage"]
    quality_service = runtime.context["quality_service"]
    provider = runtime.context["ocr_provider"]
    max_attempts = runtime.context["ocr_max_attempts"]
    minimum_accepted_score = runtime.context[
        "ocr_min_accepted_score"
    ]

    candidate_ids = state.get(
        "ocr_required_page_ids",
        [],
    )

    if not candidate_ids:
        return {
            "ocr_recovery_completed": True,
            "ocr_succeeded_page_ids": [],
            "ocr_failed_page_ids": [],
            "ocr_provider_name": provider.name,
            "workflow_status": "ocr_completed",
            "current_node": "ocr_recovery",
            "next_action": "classification",
        }

    if not provider.is_available():
        return {
            "ocr_recovery_completed": False,
            "ocr_succeeded_page_ids": [],
            "ocr_failed_page_ids": candidate_ids,
            "ocr_provider_name": provider.name,
            "workflow_status": "failed",
            "current_node": "ocr_recovery",
            "next_action": "mark_failed",
            "errors": [
                "OCR is required, but the configured OCR "
                "provider is unavailable."
            ],
        }

    recovery_service = OCRRecoveryService(
        storage=storage,
        provider=provider,
        quality_service=quality_service,
    )

    succeeded_ids: list[str] = []
    failed_ids: list[str] = []
    warnings: list[str] = []
    affected_document_ids: set[UUID] = set()

    for page_id_text in candidate_ids:
        page_id = UUID(page_id_text)

        with session_factory() as session:
            repository = DocumentRepository(session)

            row = repository.get_page_for_tenant(
                page_id=page_id,
                tenant_id=tenant_id,
            )

            if row is None:
                failed_ids.append(page_id_text)
                warnings.append(
                    f"OCR page was not found: {page_id_text}"
                )
                continue

            page, document = row
            affected_document_ids.add(document.id)

            if page.ocr_status == "succeeded":
                succeeded_ids.append(page_id_text)
                continue

            if page.ocr_attempts >= max_attempts:
                failed_ids.append(page_id_text)
                warnings.append(
                    f"{page.source_name}, page "
                    f"{page.source_page_number}: "
                    "OCR retry limit reached."
                )
                continue

            repository.mark_ocr_processing(page=page)
            session.commit()

            try:
                result, metrics = (
                    recovery_service.recover_page(
                        document=document,
                        page=page,
                    )
                )

                native_score = page.quality_score or 0.0
                ocr_score = float(metrics["score"])

                if ocr_score < minimum_accepted_score:
                    raise ValueError(
                        "OCR quality score is below the accepted "
                        f"minimum ({ocr_score:.2f} < "
                        f"{minimum_accepted_score:.2f})."
                    )

                weak_native_text = (
                    len(page.native_text)
                    < quality_service.limits.min_characters
                )

                if (
                    not weak_native_text
                    and ocr_score < native_score
                ):
                    raise ValueError(
                        "OCR quality was lower than native text."
                    )

                repository.save_ocr_success(
                    page=page,
                    result=result,
                    metrics=metrics,
                )

                session.commit()
                succeeded_ids.append(page_id_text)

            except Exception as exc:
                session.rollback()

                row = repository.get_page_for_tenant(
                    page_id=page_id,
                    tenant_id=tenant_id,
                )

                if row is not None:
                    failed_page, _document = row

                    repository.save_ocr_failure(
                        page=failed_page,
                        error=str(exc),
                    )
                    session.commit()

                failed_ids.append(page_id_text)
                warnings.append(
                    f"OCR failed for page {page_id_text}: {exc}"
                )

    with session_factory() as session:
        repository = DocumentRepository(session)

        for document_id in affected_document_ids:
            document = repository.get_for_tenant(
                document_id=document_id,
                tenant_id=tenant_id,
            )

            if document is not None:
                repository.rebuild_document_extraction(
                    document=document,
                    max_characters=runtime.context[
                        "max_document_characters"
                    ],
                )

        session.commit()

    return {
        "ocr_recovery_completed": True,
        "ocr_succeeded_page_ids": succeeded_ids,
        "ocr_failed_page_ids": failed_ids,
        "ocr_provider_name": provider.name,
        "workflow_status": "ocr_completed",
        "current_node": "ocr_recovery",
        "next_action": "classification",
        "warnings": warnings,
    }
