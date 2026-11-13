from __future__ import annotations

from collections import defaultdict
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.infrastructure.database.models import (
    Tender,
    TenderFinalizationIssue,
    TenderFinalizationRun,
    TenderNormalizedField,
    TenderRequirement,
    TenderRequirementEvidence,
    TenderRequirementRun,
    TenderVersion,
)
from app.tender_agent.schemas.finalization import (
    CoverageAuditResult,
    FinalValidationResult,
    ProfileField,
    ProfileRequirement,
    ProfileRequirementEvidence,
    TenderProfilePayload,
)


class FinalizationRepository:
    def __init__(
        self,
        session: Session,
    ) -> None:
        self.session = session

    def project_profile(
        self,
        *,
        normalization_run_id: UUID,
        requirement_run_id: UUID,
        tenant_id: str,
    ) -> TenderProfilePayload:
        requirement_run = self.session.scalar(
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
                TenderRequirementRun.normalization_run_id
                == normalization_run_id,
                TenderRequirementRun.status
                == "evidence_validated",
                Tender.tenant_id == tenant_id,
            )
        )

        if requirement_run is None:
            raise ValueError(
                "Validated requirement run was not found "
                "for tenant and normalization run."
            )

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
                .order_by(
                    TenderRequirementEvidence
                    .precedence_order,
                    TenderRequirementEvidence.page_number,
                )
            )

            for evidence in evidence_rows:
                evidence_by_requirement[
                    evidence.requirement_id
                ].append(evidence)

        profile_fields = [
            ProfileField(
                field_key=field.field_key,
                section_key=field.section_key,
                label=field.label,
                value_type=field.value_type,
                status=field.status,
                effective_value=(
                    field.effective_value_json
                ),
                effective_display_value=(
                    field.effective_display_value
                ),
                needs_review=field.needs_review,
                conflict_reason=(
                    field.conflict_reason
                ),
            )
            for field in fields
        ]

        profile_requirements = [
            ProfileRequirement(
                requirement_id=requirement.id,
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
                bidder_proof=list(
                    requirement.bidder_proof_json
                ),
                confidence=requirement.confidence,
                validation_status=(
                    requirement.validation_status
                ),
                needs_review=(
                    requirement.needs_review
                ),
                evidence=[
                    ProfileRequirementEvidence(
                        evidence_id=evidence.id,
                        source_name=(
                            evidence.source_name
                        ),
                        page_number=(
                            evidence.page_number
                        ),
                        quote=evidence.quote,
                        source_role=(
                            evidence.source_role
                        ),
                        binding_status=(
                            evidence.binding_status
                        ),
                        precedence_order=(
                            evidence.precedence_order
                        ),
                        is_valid=evidence.is_valid,
                        validation_message=(
                            evidence.validation_message
                        ),
                    )
                    for evidence in (
                        evidence_by_requirement[
                            requirement.id
                        ]
                    )
                ],
            )
            for requirement in requirements
        ]

        return TenderProfilePayload(
            tender_version_id=(
                requirement_run.tender_version_id
            ),
            normalization_run_id=(
                normalization_run_id
            ),
            requirement_run_id=requirement_run_id,
            fields=profile_fields,
            requirements=profile_requirements,
            field_count=len(profile_fields),
            requirement_count=len(
                profile_requirements
            ),
        )

    def replace_finalization(
        self,
        *,
        tenant_id: str,
        profile: TenderProfilePayload,
        coverage: CoverageAuditResult,
        validation: FinalValidationResult,
    ) -> TenderFinalizationRun:
        self._assert_source_access(
            tender_version_id=(
                profile.tender_version_id
            ),
            normalization_run_id=(
                profile.normalization_run_id
            ),
            requirement_run_id=(
                profile.requirement_run_id
            ),
            tenant_id=tenant_id,
        )

        self.session.execute(
            delete(TenderFinalizationRun).where(
                TenderFinalizationRun
                .requirement_run_id
                == profile.requirement_run_id
            )
        )
        self.session.flush()

        run = TenderFinalizationRun(
            tender_version_id=(
                profile.tender_version_id
            ),
            normalization_run_id=(
                profile.normalization_run_id
            ),
            requirement_run_id=(
                profile.requirement_run_id
            ),
            policy_id=coverage.policy_id,
            policy_version=(
                coverage.policy_version
            ),
            status=validation.status,
            ready_for_review=(
                validation.ready_for_review
            ),
            readiness_score=(
                validation.readiness_score
            ),
            field_count=profile.field_count,
            requirement_count=(
                profile.requirement_count
            ),
            issue_count=len(validation.issues),
            warning_count=sum(
                issue.severity == "warning"
                for issue in validation.issues
            ),
            error_count=sum(
                issue.severity == "error"
                for issue in validation.issues
            ),
            fatal_count=sum(
                issue.fatal
                for issue in validation.issues
            ),
            profile_json=profile.model_dump(
                mode="json"
            ),
            coverage_metrics_json=(
                coverage.metrics.model_dump(
                    mode="json"
                )
            ),
            review_reasons_json=(
                validation.review_reasons
            ),
            summary=validation.summary,
        )

        self.session.add(run)
        self.session.flush()

        self.session.add_all(
            [
                TenderFinalizationIssue(
                    finalization_run_id=run.id,
                    code=issue.code,
                    severity=issue.severity,
                    category=issue.category,
                    entity_type=issue.entity_type,
                    entity_key=issue.entity_key,
                    message=issue.message,
                    requires_review=(
                        issue.requires_review
                    ),
                    fatal=issue.fatal,
                )
                for issue in validation.issues
            ]
        )

        self.session.flush()

        return run

    def _assert_source_access(
        self,
        *,
        tender_version_id: UUID,
        normalization_run_id: UUID,
        requirement_run_id: UUID,
        tenant_id: str,
    ) -> None:
        statement = (
            select(TenderRequirementRun.id)
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
                TenderRequirementRun.normalization_run_id
                == normalization_run_id,
                TenderRequirementRun.tender_version_id
                == tender_version_id,
                TenderRequirementRun.status
                == "evidence_validated",
                TenderVersion.id == tender_version_id,
                Tender.tenant_id == tenant_id,
            )
        )

        if self.session.scalar(statement) is None:
            raise ValueError(
                "Validated finalization sources were not "
                "found for tenant."
            )
