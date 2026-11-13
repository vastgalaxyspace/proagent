from __future__ import annotations

from collections import defaultdict
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.infrastructure.database.models import (
    Tender,
    TenderFieldEvidence,
    TenderFieldResult,
    TenderFieldUnderstandingRun,
    TenderNormalizationRun,
    TenderNormalizedCandidate,
    TenderNormalizedCandidateEvidence,
    TenderNormalizedField,
    TenderVersion,
)
from app.tender_agent.domain.values import (
    NormalizationBuildResult,
    NormalizedCandidateDraft,
    NormalizedFieldDraft,
    ReconciliationBuildResult,
    SourceFieldEvidence,
    SourceFieldValue,
)


class NormalizationRepository:
    def __init__(
        self,
        session: Session,
    ) -> None:
        self.session = session

    def load_source_fields(
        self,
        *,
        understanding_run_id: UUID,
        tenant_id: str,
    ) -> tuple[
        TenderFieldUnderstandingRun,
        list[SourceFieldValue],
    ]:
        run_statement = (
            select(TenderFieldUnderstandingRun)
            .join(
                TenderVersion,
                TenderVersion.id
                == TenderFieldUnderstandingRun
                .tender_version_id,
            )
            .join(
                Tender,
                Tender.id == TenderVersion.tender_id,
            )
            .where(
                TenderFieldUnderstandingRun.id
                == understanding_run_id,
                Tender.tenant_id == tenant_id,
            )
        )

        run = self.session.scalar(run_statement)

        if run is None:
            raise ValueError(
                "Field-understanding run was not found "
                "for tenant."
            )

        fields = list(
            self.session.scalars(
                select(TenderFieldResult)
                .where(
                    TenderFieldResult
                    .understanding_run_id
                    == understanding_run_id
                )
                .order_by(
                    TenderFieldResult.section_key,
                    TenderFieldResult.field_key,
                )
            )
        )

        field_ids = [field.id for field in fields]

        evidence_by_field: dict[
            UUID,
            list[TenderFieldEvidence],
        ] = defaultdict(list)

        if field_ids:
            evidence_rows = self.session.scalars(
                select(TenderFieldEvidence)
                .where(
                    TenderFieldEvidence.field_result_id.in_(
                        field_ids
                    )
                )
                .order_by(
                    TenderFieldEvidence.precedence_order,
                    TenderFieldEvidence.page_number,
                )
            )

            for evidence in evidence_rows:
                evidence_by_field[
                    evidence.field_result_id
                ].append(evidence)

        return (
            run,
            [
                SourceFieldValue(
                    field_result_id=field.id,
                    field_key=field.field_key,
                    section_key=field.section_key,
                    label=field.label,
                    value_type=field.value_type,
                    source_status=field.status,
                    raw_value=field.raw_value_json,
                    display_value=field.display_value,
                    confidence=field.confidence,
                    needs_review=field.needs_review,
                    evidence=[
                        SourceFieldEvidence(
                            evidence_id=evidence.id,
                            chunk_id=(
                                evidence.retrieval_chunk_id
                            ),
                            logical_document_id=(
                                evidence.logical_document_id
                            ),
                            page_id=evidence.page_id,
                            source_name=(
                                evidence.source_name
                            ),
                            page_number=(
                                evidence.page_number
                            ),
                            source_role=(
                                evidence.source_role
                            ),
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
                        for evidence in evidence_by_field[
                            field.id
                        ]
                    ],
                )
                for field in fields
            ],
        )

    def replace_normalization(
        self,
        *,
        tender_version_id: UUID,
        understanding_run_id: UUID,
        result: NormalizationBuildResult,
        default_currency: str,
        default_timezone: str,
    ) -> TenderNormalizationRun:
        self.session.execute(
            delete(TenderNormalizationRun).where(
                TenderNormalizationRun
                .understanding_run_id
                == understanding_run_id
            )
        )
        self.session.flush()

        run = TenderNormalizationRun(
            tender_version_id=tender_version_id,
            understanding_run_id=understanding_run_id,
            status="normalized",
            default_currency=default_currency,
            default_timezone=default_timezone,
            normalized_field_count=(
                result.normalized_field_count
            ),
            unavailable_field_count=(
                result.unavailable_field_count
            ),
            candidate_count=result.candidate_count,
            normalization_error_count=(
                result.normalization_error_count
            ),
            reconciled_field_count=0,
            conflict_field_count=0,
            unresolved_field_count=0,
            warnings_json=result.warnings,
        )

        self.session.add(run)
        self.session.flush()

        for field in result.fields:
            stored_field = TenderNormalizedField(
                normalization_run_id=run.id,
                source_field_result_id=(
                    field.source_field_result_id
                ),
                field_key=field.field_key,
                section_key=field.section_key,
                label=field.label,
                value_type=field.value_type,
                source_status=field.source_status,
                source_confidence=(
                    field.source_confidence
                ),
                source_needs_review=(
                    field.source_needs_review
                ),
                status=field.status,
                effective_value_json=None,
                effective_display_value=None,
                needs_review=(
                    field.status == "error"
                    or field.source_needs_review
                ),
                conflict_reason=None,
                warnings_json=field.warnings,
            )

            self.session.add(stored_field)
            self.session.flush()

            for candidate in field.candidates:
                stored_candidate = (
                    TenderNormalizedCandidate(
                        normalized_field_id=(
                            stored_field.id
                        ),
                        ordinal=candidate.ordinal,
                        label=candidate.label,
                        raw_value_json=(
                            candidate.raw_value
                        ),
                        normalized_kind=(
                            candidate.normalized_kind
                        ),
                        normalized_value_json=(
                            candidate.normalized_value
                        ),
                        normalized_key=(
                            candidate.normalized_key
                        ),
                        confidence=candidate.confidence,
                        binding_status=(
                            candidate.binding_status
                        ),
                        source_role=(
                            candidate.source_role
                        ),
                        precedence_order=(
                            candidate.precedence_order
                        ),
                        retrieval_score=(
                            candidate.retrieval_score
                        ),
                        evidence_match_degraded=(
                            candidate
                            .evidence_match_degraded
                        ),
                        selected=False,
                        resolution_status="pending",
                        resolution_reason=None,
                    )
                )

                self.session.add(stored_candidate)
                self.session.flush()

                self.session.add_all(
                    [
                        TenderNormalizedCandidateEvidence(
                            normalized_candidate_id=(
                                stored_candidate.id
                            ),
                            field_evidence_id=(
                                evidence_id
                            ),
                        )
                        for evidence_id
                        in candidate.evidence_ids
                    ]
                )

        self.session.flush()

        return run

    def load_normalized_fields(
        self,
        *,
        normalization_run_id: UUID,
    ) -> list[NormalizedFieldDraft]:
        fields = list(
            self.session.scalars(
                select(TenderNormalizedField)
                .where(
                    TenderNormalizedField
                    .normalization_run_id
                    == normalization_run_id
                )
                .order_by(
                    TenderNormalizedField.section_key,
                    TenderNormalizedField.field_key,
                )
            )
        )

        field_ids = [field.id for field in fields]

        candidates_by_field: dict[
            UUID,
            list[TenderNormalizedCandidate],
        ] = defaultdict(list)

        if field_ids:
            candidates = self.session.scalars(
                select(TenderNormalizedCandidate)
                .where(
                    TenderNormalizedCandidate
                    .normalized_field_id.in_(
                        field_ids
                    )
                )
                .order_by(
                    TenderNormalizedCandidate
                    .normalized_field_id,
                    TenderNormalizedCandidate.ordinal,
                )
            )

            for candidate in candidates:
                candidates_by_field[
                    candidate.normalized_field_id
                ].append(candidate)

        return [
            NormalizedFieldDraft(
                source_field_result_id=(
                    field.source_field_result_id
                ),
                field_key=field.field_key,
                section_key=field.section_key,
                label=field.label,
                value_type=field.value_type,
                source_status=field.source_status,
                source_confidence=(
                    field.source_confidence
                ),
                source_needs_review=(
                    field.source_needs_review
                ),
                status=field.status,
                candidates=[
                    NormalizedCandidateDraft(
                        ordinal=candidate.ordinal,
                        label=candidate.label,
                        raw_value=(
                            candidate.raw_value_json
                        ),
                        normalized_kind=(
                            candidate.normalized_kind
                        ),
                        normalized_value=(
                            candidate
                            .normalized_value_json
                        ),
                        normalized_key=(
                            candidate.normalized_key
                        ),
                        confidence=(
                            candidate.confidence
                        ),
                        binding_status=(
                            candidate.binding_status
                        ),
                        source_role=(
                            candidate.source_role
                        ),
                        precedence_order=(
                            candidate.precedence_order
                        ),
                        retrieval_score=(
                            candidate.retrieval_score
                        ),
                        evidence_match_degraded=(
                            candidate
                            .evidence_match_degraded
                        ),
                        evidence_ids=[],
                    )
                    for candidate
                    in candidates_by_field[field.id]
                ],
                warnings=field.warnings_json,
            )
            for field in fields
        ]

    def apply_reconciliation(
        self,
        *,
        run: TenderNormalizationRun,
        result: ReconciliationBuildResult,
    ) -> None:
        stored_fields = {
            field.field_key: field
            for field in self.session.scalars(
                select(TenderNormalizedField)
                .where(
                    TenderNormalizedField
                    .normalization_run_id
                    == run.id
                )
            )
        }

        for reconciled in result.fields:
            stored_field = stored_fields.get(
                reconciled.field_key
            )

            if stored_field is None:
                raise ValueError(
                    "Normalized field was not found: "
                    f"{reconciled.field_key}"
                )

            stored_field.status = reconciled.status
            stored_field.effective_value_json = (
                reconciled.effective_value
            )
            stored_field.effective_display_value = (
                reconciled.effective_display_value
            )
            stored_field.needs_review = (
                reconciled.needs_review
            )
            stored_field.conflict_reason = (
                reconciled.conflict_reason
            )

            candidates = {
                candidate.ordinal: candidate
                for candidate in self.session.scalars(
                    select(
                        TenderNormalizedCandidate
                    ).where(
                        TenderNormalizedCandidate
                        .normalized_field_id
                        == stored_field.id
                    )
                )
            }

            for decision in (
                reconciled.candidate_decisions
            ):
                stored_candidate = candidates.get(
                    decision.ordinal
                )

                if stored_candidate is None:
                    raise ValueError(
                        "Normalized candidate was not "
                        "found."
                    )

                stored_candidate.selected = (
                    decision.selected
                )
                stored_candidate.resolution_status = (
                    decision.resolution_status
                )
                stored_candidate.resolution_reason = (
                    decision.resolution_reason
                )

        run.status = "reconciled"
        run.reconciled_field_count = (
            result.reconciled_field_count
        )
        run.conflict_field_count = (
            result.conflict_field_count
        )
        run.unresolved_field_count = (
            result.unresolved_field_count
        )
        run.warnings_json = [
            *run.warnings_json,
            *result.warnings,
        ]

        self.session.flush()

    def get_run(
        self,
        *,
        normalization_run_id: UUID,
        tenant_id: str,
    ) -> TenderNormalizationRun | None:
        return self.session.scalar(
            select(TenderNormalizationRun)
            .join(
                TenderVersion,
                TenderVersion.id
                == TenderNormalizationRun.tender_version_id,
            )
            .join(
                Tender,
                Tender.id == TenderVersion.tender_id,
            )
            .where(
                TenderNormalizationRun.id
                == normalization_run_id,
                Tender.tenant_id == tenant_id,
            )
        )
