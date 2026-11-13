from __future__ import annotations

from uuid import UUID

from sqlalchemy import Select, delete, select
from sqlalchemy.orm import Session

from app.infrastructure.database.models import (
    Document,
    DocumentExtraction,
    DocumentPage,
)
from app.infrastructure.providers.ocr import OCRResult
from app.tender_agent.domain.statuses import (
    DocumentExtractionStatus,
    DocumentStorageStatus,
)
from app.tender_agent.services.native_parser import (
    NativeExtractionResult,
)


class DocumentRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_for_tenant(
        self,
        *,
        document_id: UUID,
        tenant_id: str,
    ) -> Document | None:
        statement: Select[tuple[Document]] = select(Document).where(
            Document.id == document_id,
            Document.tenant_id == tenant_id,
        )
        return self.session.scalar(statement)

    def get_extraction(
        self,
        *,
        document_id: UUID,
    ) -> DocumentExtraction | None:
        statement: Select[tuple[DocumentExtraction]] = (
            select(DocumentExtraction).where(
                DocumentExtraction.document_id == document_id
            )
        )
        return self.session.scalar(statement)

    def list_for_version(
        self,
        *,
        tender_version_id: UUID,
        tenant_id: str,
    ) -> list[Document]:
        statement: Select[tuple[Document]] = (
            select(Document)
            .where(
                Document.tender_version_id == tender_version_id,
                Document.tenant_id == tenant_id,
            )
            .order_by(Document.created_at, Document.id)
        )
        return list(self.session.scalars(statement))

    def list_pages_for_documents(
        self,
        *,
        document_ids: list[UUID],
        tenant_id: str,
    ) -> list[tuple[DocumentPage, Document]]:
        if not document_ids:
            return []

        statement = (
            select(DocumentPage, Document)
            .join(
                DocumentExtraction,
                DocumentExtraction.id
                == DocumentPage.extraction_id,
            )
            .join(
                Document,
                Document.id
                == DocumentExtraction.document_id,
            )
            .where(
                Document.id.in_(document_ids),
                Document.tenant_id == tenant_id,
            )
            .order_by(
                Document.id,
                DocumentPage.page_number,
            )
        )
        return [
            (row[0], row[1])
            for row in self.session.execute(statement)
        ]

    def get_page_for_tenant(
        self,
        *,
        page_id: UUID,
        tenant_id: str,
    ) -> tuple[DocumentPage, Document] | None:
        statement = (
            select(DocumentPage, Document)
            .join(
                DocumentExtraction,
                DocumentExtraction.id
                == DocumentPage.extraction_id,
            )
            .join(
                Document,
                Document.id
                == DocumentExtraction.document_id,
            )
            .where(
                DocumentPage.id == page_id,
                Document.tenant_id == tenant_id,
            )
        )
        row = self.session.execute(statement).one_or_none()
        return None if row is None else (row[0], row[1])

    def mark_stored(
        self,
        document: Document,
        *,
        object_key: str,
        size_bytes: int,
        sha256: str,
        content_type: str,
    ) -> None:
        document.object_key = object_key
        document.size_bytes = size_bytes
        document.sha256 = sha256
        document.content_type = content_type
        document.storage_status = DocumentStorageStatus.STORED.value
        self.session.flush()

    def mark_processing(self, document: Document) -> None:
        document.extraction_status = (
            DocumentExtractionStatus.PROCESSING.value
        )
        self.session.flush()

    def save_extraction(
        self,
        *,
        document: Document,
        result: NativeExtractionResult,
    ) -> DocumentExtraction:
        extraction = self.get_extraction(document_id=document.id)

        if extraction is None:
            extraction = DocumentExtraction(
                document_id=document.id,
                status=result.status,
                extracted_text=result.text,
                character_count=len(result.text),
                page_count=len(result.pages),
                warnings_json=result.warnings,
                metadata_json=result.metadata,
            )
            self.session.add(extraction)
            self.session.flush()
        else:
            self.session.execute(
                delete(DocumentPage).where(
                    DocumentPage.extraction_id == extraction.id
                )
            )
            extraction.status = result.status
            extraction.extracted_text = result.text
            extraction.character_count = len(result.text)
            extraction.page_count = len(result.pages)
            extraction.warnings_json = result.warnings
            extraction.metadata_json = result.metadata
            self.session.flush()

        self.session.add_all(
            [
                DocumentPage(
                    extraction_id=extraction.id,
                    page_number=page.page_number,
                    source_page_number=page.source_page_number,
                    source_name=page.source_name,
                    native_text=page.text,
                    extracted_text=page.text,
                    character_count=len(page.text),
                    extraction_method=page.extraction_method,
                    ocr_required=page.ocr_required,
                    quality_score=None,
                    quality_metrics_json={},
                    ocr_status=(
                        "pending"
                        if page.ocr_required
                        else "not_required"
                    ),
                    ocr_attempts=0,
                    warnings_json=page.warnings,
                    layout_json=page.layout,
                )
                for page in result.pages
            ]
        )

        if result.status == "needs_ocr":
            document.extraction_status = (
                DocumentExtractionStatus.NEEDS_OCR.value
            )
        elif result.status == "empty":
            document.extraction_status = (
                DocumentExtractionStatus.EMPTY.value
            )
        else:
            document.extraction_status = (
                DocumentExtractionStatus.EXTRACTED.value
            )

        self.session.flush()
        return extraction

    def mark_extraction_failed(
        self,
        *,
        document: Document,
        error: str,
    ) -> None:
        document.extraction_status = (
            DocumentExtractionStatus.FAILED.value
        )
        extraction = self.get_extraction(document_id=document.id)

        if extraction is None:
            extraction = DocumentExtraction(
                document_id=document.id,
                status="failed",
                extracted_text="",
                character_count=0,
                page_count=0,
                warnings_json=[error],
                metadata_json={},
            )
            self.session.add(extraction)
        else:
            extraction.status = "failed"
            extraction.extracted_text = ""
            extraction.character_count = 0
            extraction.page_count = 0
            extraction.warnings_json = [error]
            extraction.metadata_json = {}
            self.session.execute(
                delete(DocumentPage).where(
                    DocumentPage.extraction_id == extraction.id
                )
            )
        self.session.flush()

    def save_page_quality(
        self,
        *,
        page: DocumentPage,
        score: float,
        metrics: dict,
        requires_ocr: bool,
        warning: str | None,
    ) -> None:
        if page.ocr_status == "succeeded":
            return

        page.quality_score = score
        page.quality_metrics_json = metrics
        page.ocr_required = requires_ocr
        page.ocr_status = (
            "pending" if requires_ocr else "not_required"
        )
        page.ocr_error = None

        if warning and warning not in page.warnings_json:
            page.warnings_json = [
                *page.warnings_json,
                warning,
            ]
        self.session.flush()

    def mark_ocr_processing(
        self,
        *,
        page: DocumentPage,
    ) -> None:
        page.ocr_status = "processing"
        page.ocr_attempts += 1
        page.ocr_error = None
        self.session.flush()

    def save_ocr_success(
        self,
        *,
        page: DocumentPage,
        result: OCRResult,
        metrics: dict,
    ) -> None:
        page.ocr_text = result.text
        page.ocr_provider = result.provider
        page.ocr_confidence = result.confidence
        page.ocr_status = "succeeded"
        page.ocr_required = False
        page.ocr_error = None
        page.extracted_text = result.text
        page.character_count = len(result.text)
        page.extraction_method = result.provider
        page.quality_score = float(metrics["score"])
        page.quality_metrics_json = {
            **metrics,
            "ocr_confidence": result.confidence,
        }
        page.layout_json = result.layout
        self.session.flush()

    def save_ocr_failure(
        self,
        *,
        page: DocumentPage,
        error: str,
    ) -> None:
        page.ocr_status = "failed"
        page.ocr_required = True
        page.ocr_error = error

        warning = f"OCR failed: {error}"
        if warning not in page.warnings_json:
            page.warnings_json = [
                *page.warnings_json,
                warning,
            ]
        self.session.flush()

    def rebuild_document_extraction(
        self,
        *,
        document: Document,
        max_characters: int,
    ) -> None:
        extraction = self.get_extraction(document_id=document.id)
        if extraction is None:
            raise ValueError("Document extraction was not found.")

        statement = (
            select(DocumentPage)
            .where(DocumentPage.extraction_id == extraction.id)
            .order_by(DocumentPage.page_number)
        )
        pages = list(self.session.scalars(statement))

        text = "\n\n".join(
            f"[page {page.page_number}]\n{page.extracted_text}"
            for page in pages
            if page.extracted_text
        )
        extraction.extracted_text = text[:max_characters]
        extraction.character_count = len(
            extraction.extracted_text
        )
        extraction.page_count = len(pages)

        unresolved_ocr = any(
            page.ocr_required
            for page in pages
        )
        if unresolved_ocr:
            extraction.status = "needs_ocr"
            document.extraction_status = (
                DocumentExtractionStatus.NEEDS_OCR.value
            )
        elif extraction.extracted_text:
            extraction.status = "extracted"
            document.extraction_status = (
                DocumentExtractionStatus.EXTRACTED.value
            )
        else:
            extraction.status = "empty"
            document.extraction_status = (
                DocumentExtractionStatus.EMPTY.value
            )
        self.session.flush()

