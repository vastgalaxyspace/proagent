from __future__ import annotations

from app.tender_agent.schemas.finalization import (
    CoverageAuditResult,
    FinalValidationResult,
    TenderProfilePayload,
    ValidationIssue,
)


class ValidationService:
    def validate(
        self,
        *,
        profile: TenderProfilePayload,
        coverage: CoverageAuditResult,
    ) -> FinalValidationResult:
        issues = list(coverage.issues)

        self._validate_internal_counts(
            profile=profile,
            issues=issues,
        )

        self._validate_identifiers(
            profile=profile,
            issues=issues,
        )

        fatal_issues = [
            issue
            for issue in issues
            if issue.fatal
        ]

        review_issues = [
            issue
            for issue in issues
            if issue.requires_review
        ]

        error_issues = [
            issue
            for issue in issues
            if issue.severity == "error"
        ]

        if fatal_issues:
            status = "invalid"
            ready_for_review = False
            summary = (
                "Tender understanding is structurally "
                "incomplete and cannot be handed to the "
                "Review Agent."
            )
        elif review_issues or error_issues:
            status = "review_required"
            ready_for_review = True
            summary = (
                "Tender understanding is structurally "
                "complete but contains items requiring "
                "human review."
            )
        else:
            status = "ready"
            ready_for_review = True
            summary = (
                "Tender understanding passed final "
                "validation and is ready for review."
            )

        return FinalValidationResult(
            status=status,
            ready_for_review=ready_for_review,
            readiness_score=(
                coverage.readiness_score
            ),
            summary=summary,
            issues=issues,
            review_reasons=list(
                dict.fromkeys(
                    issue.message
                    for issue in review_issues
                )
            ),
        )

    @staticmethod
    def _validate_internal_counts(
        *,
        profile: TenderProfilePayload,
        issues: list[ValidationIssue],
    ) -> None:
        if profile.field_count != len(
            profile.fields
        ):
            issues.append(
                ValidationIssue(
                    code="field_count_mismatch",
                    severity="error",
                    category="structural",
                    entity_type="profile",
                    entity_key=None,
                    message=(
                        "Stored field count does not match "
                        "the projected field collection."
                    ),
                    requires_review=True,
                    fatal=True,
                )
            )

        if profile.requirement_count != len(
            profile.requirements
        ):
            issues.append(
                ValidationIssue(
                    code="requirement_count_mismatch",
                    severity="error",
                    category="structural",
                    entity_type="profile",
                    entity_key=None,
                    message=(
                        "Stored requirement count does not "
                        "match the projected requirement "
                        "collection."
                    ),
                    requires_review=True,
                    fatal=True,
                )
            )

    @staticmethod
    def _validate_identifiers(
        *,
        profile: TenderProfilePayload,
        issues: list[ValidationIssue],
    ) -> None:
        field_keys = [
            field.field_key
            for field in profile.fields
        ]

        if len(field_keys) != len(set(field_keys)):
            issues.append(
                ValidationIssue(
                    code="duplicate_field_keys",
                    severity="error",
                    category="structural",
                    entity_type="profile",
                    entity_key=None,
                    message=(
                        "Final profile contains duplicate "
                        "field keys."
                    ),
                    requires_review=True,
                    fatal=True,
                )
            )

        requirement_codes = [
            requirement.requirement_code
            for requirement in profile.requirements
        ]

        if len(requirement_codes) != len(
            set(requirement_codes)
        ):
            issues.append(
                ValidationIssue(
                    code="duplicate_requirement_codes",
                    severity="error",
                    category="structural",
                    entity_type="profile",
                    entity_key=None,
                    message=(
                        "Final profile contains duplicate "
                        "requirement codes."
                    ),
                    requires_review=True,
                    fatal=True,
                )
            )