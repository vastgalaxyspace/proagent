from __future__ import annotations

import json
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.infrastructure.database.models import (
    Document,
    DocumentPage,
    LogicalDocument,
    LogicalDocumentPage,
    RetrievalChunk,
    RetrievalIndex,
    TenderSourcePlan,
    TenderSourcePlanMember,
    TenderAmendmentOperation,
)
from app.tender_agent.domain.retrieval import (
    RetrievalBuildResult,
    RetrievalSourcePage,
    StoredRetrievalChunk,
)


class RetrievalRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_source_pages(
        self,
        *,
        tender_version_id: UUID,
        source_plan_id: UUID,
        tenant_id: str,
    ) -> list[RetrievalSourcePage]:
        operation_statement = select(
            TenderAmendmentOperation
        ).where(
            TenderAmendmentOperation.source_plan_id
            == source_plan_id,
            TenderAmendmentOperation.validation_status
            == "validated",
        )
        operations_by_page: dict[UUID, list] = {}

        for operation in self.session.scalars(
            operation_statement
        ):
            operations_by_page.setdefault(
                operation.page_id,
                [],
            ).append(operation)

        statement = (
            select(
                TenderSourcePlanMember,
                LogicalDocument,
                Document,
                DocumentPage,
            )
            .join(
                TenderSourcePlan,
                TenderSourcePlan.id
                == TenderSourcePlanMember.source_plan_id,
            )
            .join(
                LogicalDocument,
                LogicalDocument.id
                == TenderSourcePlanMember.logical_document_id,
            )
            .join(
                Document,
                Document.id == LogicalDocument.document_id,
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
                TenderSourcePlan.id == source_plan_id,
                TenderSourcePlan.tender_version_id
                == tender_version_id,
                TenderSourcePlan.status
                == "effective_sources_built",
                Document.tender_version_id
                == tender_version_id,
                Document.tenant_id == tenant_id,
                TenderSourcePlanMember.binding_status.in_(
                    {"binding", "review_required"}
                ),
            )
            .order_by(
                TenderSourcePlanMember.precedence_order,
                LogicalDocument.id,
                LogicalDocumentPage.sequence_number,
            )
        )

        pages: list[RetrievalSourcePage] = []

        for member, logical_document, document, page in (
            self.session.execute(statement)
        ):
            page_text = (
                page.ocr_text
                if page.ocr_status == "succeeded"
                and page.ocr_text
                else page.extracted_text
            )
            amendment_annotations = [
                (
                    "[VALIDATED AMENDMENT] "
                    f"operation={operation.operation}; "
                    f"target={operation.target}; "
                    "previous_value="
                    f"{json.dumps(operation.previous_value_json, ensure_ascii=False, default=str)}; "
                    "revised_value="
                    f"{json.dumps(operation.revised_value_json, ensure_ascii=False, default=str)}; "
                    f"evidence={operation.evidence_quote}"
                )
                for operation in operations_by_page.get(
                    page.id,
                    [],
                )
            ]

            if amendment_annotations:
                page_text = "\n".join(
                    [
                        *amendment_annotations,
                        page_text or "",
                    ]
                ).strip()
            pages.append(
                RetrievalSourcePage(
                    source_plan_id=source_plan_id,
                    logical_document_id=logical_document.id,
                    document_id=document.id,
                    page_id=page.id,
                    source_role=member.source_role,
                    binding_status=member.binding_status,
                    precedence_order=member.precedence_order,
                    logical_document_title=(
                        logical_document.title
                    ),
                    source_name=logical_document.source_name,
                    page_number=page.page_number,
                    source_page_number=(
                        page.source_page_number
                    ),
                    text=page_text or "",
                )
            )

        return pages

    def replace_index(
        self,
        *,
        tender_version_id: UUID,
        source_plan_id: UUID,
        result: RetrievalBuildResult,
        embedding_provider: str,
        embedding_model: str,
        embedding_dimensions: int,
        reranker_provider: str,
        reranker_model: str,
        chunk_characters: int,
        chunk_overlap_characters: int,
    ) -> RetrievalIndex:
        self.session.execute(
            delete(RetrievalIndex).where(
                RetrievalIndex.tender_version_id
                == tender_version_id
            )
        )
        self.session.flush()

        index = RetrievalIndex(
            tender_version_id=tender_version_id,
            source_plan_id=source_plan_id,
            status="completed",
            embedding_provider=embedding_provider,
            embedding_model=embedding_model,
            embedding_dimensions=embedding_dimensions,
            reranker_provider=reranker_provider,
            reranker_model=reranker_model,
            chunk_characters=chunk_characters,
            chunk_overlap_characters=(
                chunk_overlap_characters
            ),
            chunk_count=len(result.chunks),
            indexed_page_count=result.indexed_page_count,
            skipped_page_count=result.skipped_page_count,
        )
        self.session.add(index)
        self.session.flush()

        self.session.add_all(
            [
                RetrievalChunk(
                    retrieval_index_id=index.id,
                    logical_document_id=(
                        chunk.logical_document_id
                    ),
                    document_id=chunk.document_id,
                    page_id=chunk.page_id,
                    sequence_number=chunk.sequence_number,
                    source_role=chunk.source_role,
                    binding_status=chunk.binding_status,
                    precedence_order=chunk.precedence_order,
                    logical_document_title=(
                        chunk.logical_document_title
                    ),
                    heading=chunk.heading,
                    source_name=chunk.source_name,
                    page_number=chunk.page_number,
                    source_page_number=(
                        chunk.source_page_number
                    ),
                    text_content=chunk.text,
                    token_count=chunk.token_count,
                    chunk_hash=chunk.chunk_hash,
                    embedding_json=chunk.embedding,
                )
                for chunk in result.chunks
            ]
        )
        self.session.flush()
        return index

    def list_chunks(
        self,
        *,
        retrieval_index_id: UUID,
        tenant_id: str,
    ) -> list[StoredRetrievalChunk]:
        statement = (
            select(RetrievalChunk)
            .join(
                RetrievalIndex,
                RetrievalIndex.id
                == RetrievalChunk.retrieval_index_id,
            )
            .join(
                Document,
                Document.id == RetrievalChunk.document_id,
            )
            .where(
                RetrievalIndex.id == retrieval_index_id,
                RetrievalIndex.status == "completed",
                Document.tenant_id == tenant_id,
                Document.tender_version_id
                == RetrievalIndex.tender_version_id,
            )
            .order_by(
                RetrievalChunk.precedence_order,
                RetrievalChunk.logical_document_id,
                RetrievalChunk.sequence_number,
            )
        )

        return [
            StoredRetrievalChunk(
                chunk_id=row.id,
                logical_document_id=row.logical_document_id,
                document_id=row.document_id,
                page_id=row.page_id,
                source_role=row.source_role,
                binding_status=row.binding_status,
                precedence_order=row.precedence_order,
                logical_document_title=(
                    row.logical_document_title
                ),
                heading=row.heading,
                source_name=row.source_name,
                page_number=row.page_number,
                source_page_number=row.source_page_number,
                text=row.text_content,
                embedding=list(row.embedding_json),
            )
            for row in self.session.scalars(statement).all()
        ]
