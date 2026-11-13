from __future__ import annotations

from pathlib import Path

import yaml

from app.tender_agent.schemas.field_schema import (
    TenderFieldCatalog,
)
from app.tender_agent.schemas.finalization import (
    CoverageAuditResult,
    CoverageMetrics,
    CoveragePolicy,
    TenderProfilePayload,
    ValidationIssue,
)


class CoverageService:
    def __init__(
        self,
        *,
        policy_path: Path,
    ) -> None:
        self.policy = self._load_policy(
            policy_path
        )

    def audit(
        self,
        *,
        profile: TenderProfilePayload,
        field_catalog: TenderFieldCatalog,
    ) -> CoverageAuditResult:
        issues: list[ValidationIssue] = []

        configured_fields = {
            field.key
            for _, field in field_catalog.all_fields()
        }

        fields_by_key = {
            field.field_key: field
            for field in profile.fields
        }

        reconciled_field_count = 0

        for field_key in sorted(configured_fields):
            profile_field = fields_by_key.get(field_key)

            if profile_field is None:
                issues.append(
                    ValidationIssue(
                        code="field_missing",
                        severity="warning",
                        category="field_coverage",
                        entity_type="field",
                        entity_key=field_key,
                        message=(
                            "Configured field is absent from "
                            "the final tender profile."
                        ),
                        requires_review=True,
                    )
                )
                continue

            if profile_field.status == "reconciled":
                reconciled_field_count += 1
            else:
                severity = (
                    "error"
                    if profile_field.status
                    in {"conflict", "error"}
                    else "warning"
                )

                issues.append(
                    ValidationIssue(
                        code=(
                            "field_not_reconciled"
                        ),
                        severity=severity,
                        category="field_coverage",
                        entity_type="field",
                        entity_key=field_key,
                        message=(
                            "Field is not in reconciled "
                            f"status: {profile_field.status}."
                        ),
                        requires_review=True,
                    )
                )

            if profile_field.needs_review:
                issues.append(
                    ValidationIssue(
                        code="field_requires_review",
                        severity="warning",
                        category="field_quality",
                        entity_type="field",
                        entity_key=field_key,
                        message=(
                            profile_field.conflict_reason
                            or "Field requires human review."
                        ),
                        requires_review=True,
                    )
                )

        configured_field_count = len(
            configured_fields
        )

        field_coverage_ratio = self._ratio(
            reconciled_field_count,
            configured_field_count,
        )

        if (
            field_coverage_ratio
            < self.policy.minimum_field_coverage
        ):
            issues.append(
                ValidationIssue(
                    code="field_coverage_below_threshold",
                    severity="error",
                    category="field_coverage",
                    entity_type="profile",
                    entity_key=None,
                    message=(
                        "Reconciled field coverage is "
                        f"{field_coverage_ratio:.1%}; "
                        "minimum required coverage is "
                        f"{self.policy.minimum_field_coverage:.1%}."
                    ),
                    requires_review=True,
                )
            )

        required_categories = set(
            self.policy
            .required_requirement_categories
        )

        covered_categories = {
            requirement.category_key
            for requirement in profile.requirements
        }

        for category in sorted(
            required_categories - covered_categories
        ):
            issues.append(
                ValidationIssue(
                    code="requirement_category_missing",
                    severity="error",
                    category="requirement_coverage",
                    entity_type="requirement_category",
                    entity_key=category,
                    message=(
                        "Required requirement category "
                        f"is missing: {category}."
                    ),
                    requires_review=True,
                )
            )

        category_coverage_ratio = self._ratio(
            len(
                required_categories
                & covered_categories
            ),
            len(required_categories),
        )

        validated_requirement_count = 0
        review_item_count = sum(
            field.needs_review
            for field in profile.fields
        )

        for requirement in profile.requirements:
            if requirement.needs_review:
                review_item_count += 1

                issues.append(
                    ValidationIssue(
                        code=(
                            "requirement_requires_review"
                        ),
                        severity="warning",
                        category="requirement_quality",
                        entity_type="requirement",
                        entity_key=(
                            requirement.requirement_code
                        ),
                        message=(
                            "Requirement requires human "
                            "review."
                        ),
                        requires_review=True,
                    )
                )

            if (
                requirement.validation_status
                == "invalid"
            ):
                severity = (
                    "error"
                    if requirement.obligation_level
                    == "mandatory"
                    else "warning"
                )

                issues.append(
                    ValidationIssue(
                        code=(
                            "requirement_evidence_invalid"
                        ),
                        severity=severity,
                        category="evidence_coverage",
                        entity_type="requirement",
                        entity_key=(
                            requirement.requirement_code
                        ),
                        message=(
                            "Requirement has no valid "
                            "supporting evidence."
                        ),
                        requires_review=True,
                    )
                )

            valid_evidence_count = sum(
                evidence.is_valid is True
                for evidence in requirement.evidence
            )

            if valid_evidence_count > 0:
                validated_requirement_count += 1

            if (
                valid_evidence_count == 0
                and requirement.validation_status
                != "invalid"
            ):
                issues.append(
                    ValidationIssue(
                        code="requirement_without_evidence",
                        severity=(
                            "error"
                            if requirement.obligation_level
                            == "mandatory"
                            else "warning"
                        ),
                        category="evidence_coverage",
                        entity_type="requirement",
                        entity_key=(
                            requirement.requirement_code
                        ),
                        message=(
                            "Requirement has no validated "
                            "evidence quotation."
                        ),
                        requires_review=True,
                    )
                )

        requirement_count = len(
            profile.requirements
        )

        evidence_coverage_ratio = self._ratio(
            validated_requirement_count,
            requirement_count,
        )

        if (
            evidence_coverage_ratio
            < self.policy
            .minimum_requirement_evidence_coverage
        ):
            issues.append(
                ValidationIssue(
                    code=(
                        "evidence_coverage_below_threshold"
                    ),
                    severity="error",
                    category="evidence_coverage",
                    entity_type="profile",
                    entity_key=None,
                    message=(
                        "Validated requirement evidence "
                        f"coverage is "
                        f"{evidence_coverage_ratio:.1%}; "
                        "minimum required coverage is "
                        f"{self.policy.minimum_requirement_evidence_coverage:.1%}."
                    ),
                    requires_review=True,
                )
            )

        if configured_field_count == 0:
            issues.append(
                ValidationIssue(
                    code="no_configured_fields",
                    severity="error",
                    category="structural",
                    entity_type="profile",
                    entity_key=None,
                    message=(
                        "No configured tender fields "
                        "were available."
                    ),
                    requires_review=True,
                    fatal=True,
                )
            )

        if not profile.fields:
            issues.append(
                ValidationIssue(
                    code="profile_has_no_fields",
                    severity="error",
                    category="structural",
                    entity_type="profile",
                    entity_key=None,
                    message=(
                        "Final profile contains no tender "
                        "fields."
                    ),
                    requires_review=True,
                    fatal=True,
                )
            )

        if not profile.requirements:
            issues.append(
                ValidationIssue(
                    code="profile_has_no_requirements",
                    severity="error",
                    category="structural",
                    entity_type="profile",
                    entity_key=None,
                    message=(
                        "Final profile contains no tender "
                        "requirements."
                    ),
                    requires_review=True,
                    fatal=True,
                )
            )

        total_reviewable_items = (
            len(profile.fields)
            + len(profile.requirements)
        )

        review_ratio = self._ratio(
            review_item_count,
            total_reviewable_items,
        )

        readiness_score = self._score(
            field_coverage_ratio=(
                field_coverage_ratio
            ),
            category_coverage_ratio=(
                category_coverage_ratio
            ),
            evidence_coverage_ratio=(
                evidence_coverage_ratio
            ),
            review_ratio=review_ratio,
        )

        if (
            readiness_score
            < self.policy.minimum_readiness_score
        ):
            issues.append(
                ValidationIssue(
                    code="readiness_score_below_threshold",
                    severity="warning",
                    category="readiness",
                    entity_type="profile",
                    entity_key=None,
                    message=(
                        f"Readiness score is "
                        f"{readiness_score:.2f}; minimum "
                        f"target is "
                        f"{self.policy.minimum_readiness_score:.2f}."
                    ),
                    requires_review=True,
                )
            )

        return CoverageAuditResult(
            policy_id=self.policy.policy_id,
            policy_version=(
                self.policy.policy_version
            ),
            readiness_score=readiness_score,
            metrics=CoverageMetrics(
                configured_field_count=(
                    configured_field_count
                ),
                reconciled_field_count=(
                    reconciled_field_count
                ),
                field_coverage_ratio=(
                    field_coverage_ratio
                ),
                required_category_count=len(
                    required_categories
                ),
                covered_category_count=len(
                    required_categories
                    & covered_categories
                ),
                category_coverage_ratio=(
                    category_coverage_ratio
                ),
                requirement_count=(
                    requirement_count
                ),
                validated_requirement_count=(
                    validated_requirement_count
                ),
                evidence_coverage_ratio=(
                    evidence_coverage_ratio
                ),
                review_item_count=(
                    review_item_count
                ),
                review_ratio=review_ratio,
            ),
            issues=issues,
            warning_count=sum(
                issue.severity == "warning"
                for issue in issues
            ),
            error_count=sum(
                issue.severity == "error"
                for issue in issues
            ),
            fatal_count=sum(
                issue.fatal
                for issue in issues
            ),
        )

    def _score(
        self,
        *,
        field_coverage_ratio: float,
        category_coverage_ratio: float,
        evidence_coverage_ratio: float,
        review_ratio: float,
    ) -> float:
        weights = self.policy.weights

        score = (
            field_coverage_ratio
            * weights.field_coverage
            + category_coverage_ratio
            * weights.category_coverage
            + evidence_coverage_ratio
            * weights.evidence_coverage
            + max(0.0, 1.0 - review_ratio)
            * weights.review_quality
        )

        return round(
            max(0.0, min(score, 100.0)),
            2,
        )

    @staticmethod
    def _ratio(
        numerator: int,
        denominator: int,
    ) -> float:
        if denominator <= 0:
            return 0.0

        return numerator / denominator

    @staticmethod
    def _load_policy(
        path: Path,
    ) -> CoveragePolicy:
        if not path.is_file():
            raise RuntimeError(
                "Coverage policy was not found: "
                f"{path}"
            )

        payload = yaml.safe_load(
            path.read_text(encoding="utf-8")
        )

        return CoveragePolicy.model_validate(
            payload
        )
