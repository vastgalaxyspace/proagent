from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.infrastructure.database.models import (
    DocumentClassification,
    PageClassification,
)
from app.tender_agent.domain.classification import (
    DocumentClassificationDecision,
    PageClassificationDecision,
)


class ClassificationRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_for_document(
        self,
        *,
        document_id: UUID,
    ) -> DocumentClassification | None:
        statement = select(DocumentClassification).where(
            DocumentClassification.document_id
            == document_id
        )

        return self.session.scalar(statement)

    def save_document_classification(
        self,
        *,
        aggregate: DocumentClassificationDecision,
        page_decisions: list[
            PageClassificationDecision
        ],
    ) -> DocumentClassification:
        classification = self.get_for_document(
            document_id=aggregate.document_id
        )

        if classification is None:
            classification = DocumentClassification(
                document_id=aggregate.document_id,
                primary_document_type=(
                    aggregate.primary_document_type
                ),
                content_role=aggregate.content_role,
                confidence=aggregate.confidence,
                needs_review=aggregate.needs_review,
                type_breakdown_json=(
                    aggregate.type_breakdown
                ),
            )

            self.session.add(classification)
            self.session.flush()

        else:
            classification.primary_document_type = (
                aggregate.primary_document_type
            )
            classification.content_role = (
                aggregate.content_role
            )
            classification.confidence = (
                aggregate.confidence
            )
            classification.needs_review = (
                aggregate.needs_review
            )
            classification.type_breakdown_json = (
                aggregate.type_breakdown
            )

            self.session.execute(
                delete(PageClassification).where(
                    PageClassification
                    .document_classification_id
                    == classification.id
                )
            )

            self.session.flush()

        self.session.add_all(
            [
                PageClassification(
                    document_classification_id=(
                        classification.id
                    ),
                    page_id=decision.page_id,
                    document_type=decision.document_type,
                    content_role=decision.content_role,
                    title=decision.title,
                    confidence=decision.confidence,
                    reason=decision.reason,
                    signals_json=decision.signals,
                    classification_method=(
                        decision.classification_method
                    ),
                )
                for decision in page_decisions
            ]
        )

        self.session.flush()
        return classification