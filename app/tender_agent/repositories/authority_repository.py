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
)
from app.tender_agent.domain.authority import (
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

        plan.status = "effective_sources_built"
        plan.needs_review = draft.needs_review
        plan.warnings_json = draft.warnings

        self.session.flush()

        return members