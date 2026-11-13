from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)


IssueSeverity = Literal[
    "info",
    "warning",
    "error",
]

FinalValidationStatus = Literal[
    "ready",
    "review_required",
    "invalid",
]


class CoverageWeights(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field_coverage: float = Field(
        ge=0.0,
        le=100.0,
    )
    category_coverage: float = Field(
        ge=0.0,
        le=100.0,
    )
    evidence_coverage: float = Field(
        ge=0.0,
        le=100.0,
    )
    review_quality: float = Field(
        ge=0.0,
        le=100.0,
    )

    @model_validator(mode="after")
    def validate_total(
        self,
    ) -> "CoverageWeights":
        total = (
            self.field_coverage
            + self.category_coverage
            + self.evidence_coverage
            + self.review_quality
        )

        if abs(total - 100.0) > 0.001:
            raise ValueError(
                "Coverage weights must total 100."
            )

        return self


class CoveragePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    policy_id: str = Field(
        min_length=1,
        max_length=255,
    )
    policy_version: str = Field(
        min_length=1,
        max_length=100,
    )

    required_requirement_categories: list[str] = (
        Field(min_length=1)
    )

    minimum_field_coverage: float = Field(
        ge=0.0,
        le=1.0,
    )
    minimum_requirement_evidence_coverage: float = (
        Field(
            ge=0.0,
            le=1.0,
        )
    )
    minimum_readiness_score: float = Field(
        ge=0.0,
        le=100.0,
    )

    weights: CoverageWeights


class ProfileFieldEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: UUID
    source_name: str
    page_number: int
    quote: str

    source_role: str
    binding_status: str
    precedence_order: int


class ProfileField(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field_key: str
    section_key: str
    label: str
    value_type: str

    status: str
    effective_value: Any | None = None
    effective_display_value: str | None = None

    needs_review: bool
    conflict_reason: str | None = None


class ProfileRequirementEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: UUID
    source_name: str
    page_number: int
    quote: str

    source_role: str
    binding_status: str
    precedence_order: int

    is_valid: bool | None
    validation_message: str | None


class ProfileRequirement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requirement_id: UUID
    requirement_code: str

    category_key: str
    category_label: str

    title: str
    requirement_text: str
    obligation_level: str

    condition_text: str | None = None
    bidder_proof: list[str] = Field(
        default_factory=list
    )

    confidence: float = Field(
        ge=0.0,
        le=1.0,
    )

    validation_status: str
    needs_review: bool

    evidence: list[
        ProfileRequirementEvidence
    ] = Field(default_factory=list)


class TenderProfilePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tender_version_id: UUID
    normalization_run_id: UUID
    requirement_run_id: UUID

    fields: list[ProfileField] = Field(
        default_factory=list
    )
    requirements: list[ProfileRequirement] = Field(
        default_factory=list
    )

    field_count: int = 0
    requirement_count: int = 0


class ValidationIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    severity: IssueSeverity
    category: str

    entity_type: str
    entity_key: str | None = None

    message: str

    requires_review: bool = False
    fatal: bool = False


class CoverageMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    configured_field_count: int
    reconciled_field_count: int
    field_coverage_ratio: float

    required_category_count: int
    covered_category_count: int
    category_coverage_ratio: float

    requirement_count: int
    validated_requirement_count: int
    evidence_coverage_ratio: float

    review_item_count: int
    review_ratio: float


class CoverageAuditResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    policy_id: str
    policy_version: str

    readiness_score: float = Field(
        ge=0.0,
        le=100.0,
    )

    metrics: CoverageMetrics
    issues: list[ValidationIssue] = Field(
        default_factory=list
    )

    warning_count: int = 0
    error_count: int = 0
    fatal_count: int = 0


class FinalValidationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: FinalValidationStatus
    ready_for_review: bool

    readiness_score: float = Field(
        ge=0.0,
        le=100.0,
    )

    summary: str

    issues: list[ValidationIssue] = Field(
        default_factory=list
    )

    review_reasons: list[str] = Field(
        default_factory=list
    )