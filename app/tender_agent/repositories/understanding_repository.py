from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.infrastructure.database.models import (
    Tender,
    TenderFieldEvidence,
    TenderFieldResult,
    TenderFieldUnderstandingRun,
    TenderVersion,
)
from app.tender_agent.domain.values import (
    FieldUnderstandingBuildResult,
)
from app.tender_agent.schemas.field_schema import (
    TenderFieldCatalog,
)


class UnderstandingRepository:
    def __init__(
        self,
        session: Session,
    ) -> None:
        self.session = session

    def replace_understanding(
        self,
        *,
        tender_version_id: UUID,
        retrieval_index_id: UUID,
        tenant_id: str,
        catalog: TenderFieldCatalog,
        result: FieldUnderstandingBuildResult,
        llm_provider: str,
        llm_model: str,
    ) -> TenderFieldUnderstandingRun:
        self._assert_tenant_access(
            tender_version_id=tender_version_id,
            tenant_id=tenant_id,
        )

        existing_ids = select(
            TenderFieldUnderstandingRun.id
        ).where(
            TenderFieldUnderstandingRun.tender_version_id
            == tender_version_id
        )

        self.session.execute(
            delete(TenderFieldUnderstandingRun).where(
                TenderFieldUnderstandingRun.id.in_(
                    existing_ids
                )
            )
        )

        self.session.flush()

        run = TenderFieldUnderstandingRun(
            tender_version_id=tender_version_id,
            retrieval_index_id=retrieval_index_id,
            catalog_schema_id=catalog.schema_id,
            catalog_schema_version=(
                catalog.schema_version
            ),
            status="completed",
            llm_provider=llm_provider,
            llm_model=llm_model,
            configured_count=result.configured_count,
            found_count=result.found_count,
            not_found_count=result.not_found_count,
            ambiguous_count=result.ambiguous_count,
            error_count=result.error_count,
            warnings_json=result.warnings,
        )

        self.session.add(run)
        self.session.flush()

        for field in result.fields:
            stored_field = TenderFieldResult(
                understanding_run_id=run.id,
                field_key=field.field_key,
                section_key=field.section_key,
                label=field.label,
                value_type=field.value_type,
                status=field.status,
                raw_value_json=field.raw_value,
                display_value=field.display_value,
                confidence=field.confidence,
                explanation=field.explanation,
                search_query=field.search_query,
                needs_review=field.needs_review,
            )

            self.session.add(stored_field)
            self.session.flush()

            evidence_rows = [
                TenderFieldEvidence(
                    field_result_id=stored_field.id,
                    retrieval_chunk_id=evidence.chunk_id,
                    logical_document_id=(
                        evidence.logical_document_id
                    ),
                    page_id=evidence.page_id,
                    source_name=evidence.source_name,
                    page_number=evidence.page_number,
                    source_role=evidence.source_role,
                    binding_status=(
                        evidence.binding_status
                    ),
                    precedence_order=(
                        evidence.precedence_order
                    ),
                    quote=evidence.quote,
                    retrieval_score=(
                        evidence.retrieval_score
                    ),
                )
                for evidence in field.evidence
            ]

            self.session.add_all(evidence_rows)

        self.session.flush()

        return run

    def _assert_tenant_access(
        self,
        *,
        tender_version_id: UUID,
        tenant_id: str,
    ) -> None:
        statement = (
            select(TenderVersion.id)
            .join(
                Tender,
                Tender.id == TenderVersion.tender_id,
            )
            .where(
                TenderVersion.id == tender_version_id,
                Tender.tenant_id == tenant_id,
            )
        )

        if self.session.scalar(statement) is None:
            raise ValueError(
                "Tender version was not found for tenant."
            )