from __future__ import annotations

from collections import defaultdict
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.infrastructure.database.models import (
    Tender,
    TenderNormalizationRun,
    RetrievalIndex,
    TenderRequirement,
    TenderRequirementEvidence,
    TenderRequirementRun,
    TenderVersion,
)
from app.tender_agent.domain.values import (
    EvidenceValidationBuildResult,
    RequirementBuildResult,
    StoredRequirement,
    StoredRequirementEvidence,
)


class RequirementRepository:
    def __init__(
        self,
        session: Session,
    ) -> None:
        self.session = session

    def replace_requirements(
        self,
        *,
        tender_version_id: UUID,
        normalization_run_id: UUID,
        retrieval_index_id: UUID,
        tenant_id: str,
        catalog_schema_id: str,
        catalog_schema_version: str,
        llm_provider: str,
        llm_model: str,
        result: RequirementBuildResult,
    ) -> TenderRequirementRun:
        self._assert_tenant_access(
            tender_version_id=tender_version_id,
            normalization_run_id=(
                normalization_run_id
            ),
            retrieval_index_id=retrieval_index_id,
            tenant_id=tenant_id,
        )

        self.session.execute(
            delete(TenderRequirementRun).where(
                TenderRequirementRun.normalization_run_id
                == normalization_run_id
            )
        )
        self.session.flush()

        run = TenderRequirementRun(
            tender_version_id=tender_version_id,
            normalization_run_id=(
                normalization_run_id
            ),
            retrieval_index_id=retrieval_index_id,
            catalog_schema_id=catalog_schema_id,
            catalog_schema_version=(
                catalog_schema_version
            ),
            status="requirements_extracted",
            llm_provider=llm_provider,
            llm_model=llm_model,
            requirement_count=(
                result.requirement_count
            ),
            mandatory_count=result.mandatory_count,
            conditional_count=(
                result.conditional_count
            ),
            informational_count=(
                result.informational_count
            ),
            validated_count=0,
            review_count=0,
            invalid_count=0,
            warnings_json=result.warnings,
        )

        self.session.add(run)
        self.session.flush()

        for requirement in result.requirements:
            stored_requirement = TenderRequirement(
                requirement_run_id=run.id,
                requirement_code=(
                    requirement.requirement_code
                ),
                category_key=(
                    requirement.category_key
                ),
                category_label=(
                    requirement.category_label
                ),
                title=requirement.title,
                requirement_text=(
                    requirement.requirement_text
                ),
                obligation_level=(
                    requirement.obligation_level
                ),
                condition_text=(
                    requirement.condition_text
                ),
                bidder_proof_json=(
                    requirement.bidder_proof
                ),
                confidence=requirement.confidence,
                validation_status=(
                    "pending_validation"
                ),
                needs_review=(
                    requirement.needs_review
                ),
                warnings_json=requirement.warnings,
            )

            self.session.add(stored_requirement)
            self.session.flush()

            self.session.add_all(
                [
                    TenderRequirementEvidence(
                        requirement_id=(
                            stored_requirement.id
                        ),
                        retrieval_chunk_id=(
                            evidence.chunk_id
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
                        is_valid=None,
                        validation_message=None,
                    )
                    for evidence in requirement.evidence
                ]
            )

        self.session.flush()

        return run

    def load_for_validation(
        self,
        *,
        requirement_run_id: UUID,
        tenant_id: str,
    ) -> tuple[
        TenderRequirementRun,
        list[StoredRequirement],
    ]:
        run = self.session.scalar(
            select(TenderRequirementRun)
            .join(
                TenderVersion,
                TenderVersion.id
                == TenderRequirementRun
                .tender_version_id,
            )
            .join(
                Tender,
                Tender.id == TenderVersion.tender_id,
            )
            .where(
                TenderRequirementRun.id
                == requirement_run_id,
                Tender.tenant_id == tenant_id,
            )
        )

        if run is None:
            raise ValueError(
                "Requirement run was not found for tenant."
            )

        requirements = list(
            self.session.scalars(
                select(TenderRequirement)
                .where(
                    TenderRequirement.requirement_run_id
                    == requirement_run_id
                )
                .order_by(
                    TenderRequirement.category_key,
                    TenderRequirement.requirement_code,
                )
            )
        )

        requirement_ids = [
            requirement.id
            for requirement in requirements
        ]

        evidence_by_requirement: dict[
            UUID,
            list[TenderRequirementEvidence],
        ] = defaultdict(list)

        if requirement_ids:
            evidence_rows = self.session.scalars(
                select(TenderRequirementEvidence)
                .where(
                    TenderRequirementEvidence
                    .requirement_id.in_(
                        requirement_ids
                    )
                )
            )

            for evidence in evidence_rows:
                evidence_by_requirement[
                    evidence.requirement_id
                ].append(evidence)

        return (
            run,
            [
                StoredRequirement(
                    requirement_id=requirement.id,
                    requirement_code=(
                        requirement.requirement_code
                    ),
                    confidence=(
                        requirement.confidence
                    ),
                    extraction_needs_review=(
                        requirement.needs_review
                    ),
                    evidence=[
                        StoredRequirementEvidence(
                            evidence_id=evidence.id,
                            chunk_id=(
                                evidence
                                .retrieval_chunk_id
                            ),
                            logical_document_id=(
                                evidence
                                .logical_document_id
                            ),
                            page_id=evidence.page_id,
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
                        )
                        for evidence in (
                            evidence_by_requirement[
                                requirement.id
                            ]
                        )
                    ],
                )
                for requirement in requirements
            ],
        )

    def apply_validation(
        self,
        *,
        run: TenderRequirementRun,
        result: EvidenceValidationBuildResult,
    ) -> None:
        requirements = {
            requirement.id: requirement
            for requirement in self.session.scalars(
                select(TenderRequirement).where(
                    TenderRequirement.requirement_run_id
                    == run.id
                )
            )
        }

        evidence_ids = [
            evidence_id
            for decision in result.requirements
            for evidence_id in (
                item.evidence_id
                for item in (
                    decision.evidence_decisions
                )
            )
        ]

        evidence_rows = (
            {
                evidence.id: evidence
                for evidence in self.session.scalars(
                    select(
                        TenderRequirementEvidence
                    ).where(
                        TenderRequirementEvidence.id.in_(
                            evidence_ids
                        )
                    )
                )
            }
            if evidence_ids
            else {}
        )

        for decision in result.requirements:
            requirement = requirements.get(
                decision.requirement_id
            )

            if requirement is None:
                raise ValueError(
                    "Requirement disappeared during "
                    "evidence validation."
                )

            requirement.validation_status = (
                decision.validation_status
            )
            requirement.needs_review = (
                decision.needs_review
            )
            requirement.warnings_json = [
                *requirement.warnings_json,
                *decision.warnings,
            ]

            for evidence_decision in (
                decision.evidence_decisions
            ):
                evidence = evidence_rows.get(
                    evidence_decision.evidence_id
                )

                if evidence is None:
                    raise ValueError(
                        "Requirement evidence disappeared "
                        "during validation."
                    )

                evidence.is_valid = (
                    evidence_decision.is_valid
                )
                evidence.validation_message = (
                    evidence_decision
                    .validation_message
                )

        run.status = "evidence_validated"
        run.validated_count = result.validated_count
        run.review_count = result.review_count
        run.invalid_count = result.invalid_count
        run.warnings_json = [
            *run.warnings_json,
            *result.warnings,
        ]

        self.session.flush()

    def _assert_tenant_access(
        self,
        *,
        tender_version_id: UUID,
        normalization_run_id: UUID,
        retrieval_index_id: UUID,
        tenant_id: str,
    ) -> None:
        statement = (
            select(TenderNormalizationRun.id)
            .join(
                TenderVersion,
                TenderVersion.id
                == TenderNormalizationRun
                .tender_version_id,
            )
            .join(
                Tender,
                Tender.id == TenderVersion.tender_id,
            )
            .join(
                RetrievalIndex,
                RetrievalIndex.tender_version_id
                == TenderVersion.id,
            )
            .where(
                TenderNormalizationRun.id
                == normalization_run_id,
                TenderNormalizationRun.tender_version_id
                == tender_version_id,
                TenderNormalizationRun.status
                == "reconciled",
                RetrievalIndex.id == retrieval_index_id,
                RetrievalIndex.status == "completed",
                Tender.tenant_id == tenant_id,
            )
        )

        if self.session.scalar(statement) is None:
            raise ValueError(
                "Reconciled normalization run was not "
                "found for tenant."
            )
