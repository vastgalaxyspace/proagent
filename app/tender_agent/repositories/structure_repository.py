from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.infrastructure.database.models import (
    Document,
    DocumentExtraction,
    DocumentPage,
    LogicalDocument,
    LogicalDocumentPage,
    PageClassification,
)
from app.tender_agent.domain.structure import (
    ClassifiedPage,
    LogicalDocumentDraft,
)


class StructureRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_classified_pages(
        self,
        *,
        document_ids: list[UUID],
        tenant_id: str,
    ) -> list[ClassifiedPage]:
        if not document_ids:
            return []

        statement = (
            select(
                DocumentPage,
                PageClassification,
                Document,
            )
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
            .join(
                PageClassification,
                PageClassification.page_id
                == DocumentPage.id,
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
            ClassifiedPage(
                page_id=page.id,
                document_id=document.id,
                page_number=page.page_number,
                source_page_number=(
                    page.source_page_number
                ),
                source_name=page.source_name,
                document_type=classification.document_type,
                content_role=classification.content_role,
                title=classification.title,
                confidence=classification.confidence,
                reason=classification.reason,
                classification_method=(
                    classification.classification_method
                ),
            )
            for page, classification, document
            in self.session.execute(statement)
        ]

    def replace_document_structure(
        self,
        *,
        document_id: UUID,
        drafts: list[LogicalDocumentDraft],
    ) -> list[LogicalDocument]:
        self.session.execute(
            delete(LogicalDocument).where(
                LogicalDocument.document_id
                == document_id
            )
        )

        self.session.flush()

        logical_documents: list[LogicalDocument] = []

        for draft in drafts:
            logical_document = LogicalDocument(
                document_id=draft.document_id,
                sequence_number=draft.sequence_number,
                document_type=draft.document_type,
                content_role=draft.content_role,
                title=draft.title,
                source_name=draft.source_name,
                start_page_number=(
                    draft.start_page_number
                ),
                end_page_number=draft.end_page_number,
                start_source_page_number=(
                    draft.start_source_page_number
                ),
                end_source_page_number=(
                    draft.end_source_page_number
                ),
                page_count=draft.page_count,
                confidence=draft.confidence,
                needs_review=draft.needs_review,
                boundary_reason=draft.boundary_reason,
            )

            self.session.add(logical_document)
            self.session.flush()

            self.session.add_all(
                [
                    LogicalDocumentPage(
                        logical_document_id=(
                            logical_document.id
                        ),
                        page_id=page_id,
                        sequence_number=index,
                    )
                    for index, page_id in enumerate(
                        draft.page_ids,
                        start=1,
                    )
                ]
            )

            logical_documents.append(logical_document)

        self.session.flush()
        return logical_documents