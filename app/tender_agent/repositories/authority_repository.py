from __future__ import annotations

from collections import defaultdict
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.infrastructure.database.models import (
    Document,
    DocumentPage,
    LogicalDocument,
    LogicalDocumentPage,
    TenderSourcePlan,
    TenderSourcePlanMember,
    TenderAmendmentOperation,
)
from app.tender_agent.domain.authority import (
    AmendmentSourcePage,
    BaseTenderSelection,
    EffectiveTenderPlanDraft,
    TenderSourceCandidate,
)


class AuthorityRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_candidates(
        self,
        *,
        tender_version_id: UUID,
        tenant_id: str,
    ) -> list[TenderSourceCandidate]:
        statement = (
            select(
                LogicalDocument,
                Document,
                DocumentPage,
                LogicalDocumentPage,
            )
            .join(
                Document,
                Document.id
                == LogicalDocument.document_id,
            )
            .join(
                LogicalDocumentPage,
                LogicalDocumentPage.logical_document_id
                == LogicalDocument.id,
            )
            .join(
                DocumentPage,
                DocumentPage.id
                == LogicalDocumentPage.page_id,
            )
            .where(
                Document.tender_version_id
                == tender_version_id,
                Document.tenant_id == tenant_id,
            )
            .order_by(
                Document.created_at,
                Document.id,
                LogicalDocument.sequence_number,
                LogicalDocumentPage.sequence_number,
            )
        )

        grouped: dict[
            UUID,
            tuple[
                LogicalDocument,
                Document,
                list[DocumentPage],
            ],
        ] = {}

        order: list[UUID] = []

        for (
            logical_document,
            document,
            page,
            _mapping,
        ) in self.session.execute(statement):
            if logical_document.id not in grouped:
                grouped[logical_document.id] = (
                    logical_document,
                    document,
                    [],
                )
                order.append(logical_document.id)

            grouped[logical_document.id][2].append(page)

        candidates: list[TenderSourceCandidate] = []

        for sequence_number, logical_id in enumerate(
            order,
            start=1,
        ):
            logical_document, document, pages = grouped[
                logical_id
            ]

            combined_text = "\n\n".join(
                page.extracted_text
                for page in pages
                if page.extracted_text
            )

            candidates.append(
                TenderSourceCandidate(
                    logical_document_id=(
                        logical_document.id
                    ),
                    document_id=document.id,
                    sequence_number=sequence_number,
                    document_type=(
                        logical_document.document_type
                    ),
                    content_role=(
                        logical_document.content_role
                    ),
                    title=logical_document.title,
                    source_name=(
                        logical_document.source_name
                    ),
                    page_count=logical_document.page_count,
                    confidence=logical_document.confidence,
                    needs_review=(
                        logical_document.needs_review
                    ),
                    text=combined_text,
                    pages=[
                        AmendmentSourcePage(
                            page_id=page.id,
                            page_number=page.page_number,
                            source_page_number=(
                                page.source_page_number
                            ),
                            text=page.extracted_text or "",
                        )
                        for page in pages
                    ],
                )
            )

        return candidates

    def get_plan(
        self,
        *,
        source_plan_id: UUID,
    ) -> TenderSourcePlan | None:
        statement = select(TenderSourcePlan).where(
            TenderSourcePlan.id == source_plan_id
        )

        return self.session.scalar(statement)

    def save_base_selection(
        self,
        *,
        tender_version_id: UUID,
        selection: BaseTenderSelection,
    ) -> TenderSourcePlan:
        existing_statement = select(
            TenderSourcePlan
        ).where(
            TenderSourcePlan.tender_version_id
            == tender_version_id
        )

        existing = self.session.scalar(
            existing_statement
        )

        if existing is not None:
            self.session.delete(existing)
            self.session.flush()

        plan = TenderSourcePlan(
            tender_version_id=tender_version_id,
            primary_base_logical_document_id=(
                selection.primary_logical_document_id
            ),
            status="base_selected",
            confidence=selection.confidence,
            needs_review=selection.needs_review,
            selection_reason=selection.reason,
            warnings_json=[],
        )

        self.session.add(plan)
        self.session.flush()

        return plan

    def finalize_plan(
        self,
        *,
        plan: TenderSourcePlan,
        draft: EffectiveTenderPlanDraft,
    ) -> list[TenderSourcePlanMember]:
        self.session.execute(
            delete(TenderSourcePlanMember).where(
                TenderSourcePlanMember.source_plan_id
                == plan.id
            )
        )
        self.session.execute(
            delete(TenderAmendmentOperation).where(
                TenderAmendmentOperation.source_plan_id
                == plan.id
            )
        )

        members = [
            TenderSourcePlanMember(
                source_plan_id=plan.id,
                logical_document_id=(
                    member.logical_document_id
                ),
                source_role=member.source_role,
                precedence_order=(
                    member.precedence_order
                ),
                binding_status=member.binding_status,
                issued_at=member.issued_at,
                reference_number=member.reference_number,
                confidence=member.confidence,
                reason=member.reason,
            )
            for member in draft.members
        ]

        self.session.add_all(members)
        self.session.add_all(
            [
                TenderAmendmentOperation(
                    source_plan_id=plan.id,
                    logical_document_id=(
                        operation.logical_document_id
                    ),
                    page_id=operation.page_id,
                    operation=operation.operation,
                    target=operation.target,
                    previous_value_json=(
                        operation.previous_value
                    ),
                    revised_value_json=(
                        operation.revised_value
                    ),
                    evidence_quote=(
                        operation.evidence_quote
                    ),
                    confidence=operation.confidence,
                    validation_status=(
                        operation.validation_status
                    ),
                    reason=operation.reason,
                )
                for operation in draft.operations
            ]
        )

        plan.status = "effective_sources_built"
        plan.needs_review = draft.needs_review
        plan.warnings_json = draft.warnings

        self.session.flush()

        return members
