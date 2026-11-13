from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID


@dataclass(frozen=True)
class FieldEvidenceDraft:
    chunk_id: UUID
    logical_document_id: UUID
    page_id: UUID

    source_name: str
    page_number: int

    source_role: str
    binding_status: str
    precedence_order: int

    quote: str
    retrieval_score: float


@dataclass(frozen=True)
class FieldUnderstandingDraft:
    field_key: str
    section_key: str

    label: str
    value_type: str

    status: str
    raw_value: Any | None
    display_value: str | None

    confidence: float
    explanation: str
    search_query: str

    needs_review: bool

    evidence: list[FieldEvidenceDraft] = field(
        default_factory=list
    )


@dataclass(frozen=True)
class FieldUnderstandingBuildResult:
    fields: list[FieldUnderstandingDraft]

    configured_count: int
    found_count: int
    not_found_count: int
    ambiguous_count: int
    error_count: int

    review_field_keys: list[str]
    warnings: list[str]

@dataclass(frozen=True)
class SourceFieldEvidence:
    evidence_id: UUID
    chunk_id: UUID
    logical_document_id: UUID
    page_id: UUID

    source_name: str
    page_number: int
    source_role: str
    binding_status: str
    precedence_order: int

    quote: str
    retrieval_score: float


@dataclass(frozen=True)
class SourceFieldValue:
    field_result_id: UUID
    field_key: str
    section_key: str
    label: str
    value_type: str

    source_status: str
    raw_value: Any | None
    display_value: str | None

    confidence: float
    needs_review: bool

    evidence: list[SourceFieldEvidence] = field(
        default_factory=list
    )


@dataclass(frozen=True)
class NormalizedCandidateDraft:
    ordinal: int

    label: str | None
    raw_value: Any

    normalized_kind: str
    normalized_value: Any
    normalized_key: str

    confidence: float

    binding_status: str | None
    source_role: str | None
    precedence_order: int | None
    retrieval_score: float | None

    evidence_match_degraded: bool

    evidence_ids: list[UUID] = field(
        default_factory=list
    )


@dataclass(frozen=True)
class NormalizedFieldDraft:
    source_field_result_id: UUID

    field_key: str
    section_key: str
    label: str
    value_type: str

    source_status: str
    source_confidence: float
    source_needs_review: bool

    status: str
    candidates: list[NormalizedCandidateDraft]

    warnings: list[str] = field(
        default_factory=list
    )


@dataclass(frozen=True)
class NormalizationBuildResult:
    fields: list[NormalizedFieldDraft]

    normalized_field_count: int
    unavailable_field_count: int
    candidate_count: int
    normalization_error_count: int

    review_field_keys: list[str]
    warnings: list[str]


@dataclass(frozen=True)
class ReconciledCandidateDraft:
    ordinal: int
    selected: bool
    resolution_status: str
    resolution_reason: str


@dataclass(frozen=True)
class ReconciledFieldDraft:
    field_key: str

    status: str
    effective_value: Any | None
    effective_display_value: str | None

    needs_review: bool
    conflict_reason: str | None

    candidate_decisions: list[
        ReconciledCandidateDraft
    ]


@dataclass(frozen=True)
class ReconciliationBuildResult:
    fields: list[ReconciledFieldDraft]

    reconciled_field_count: int
    conflict_field_count: int
    unresolved_field_count: int

    conflict_field_keys: list[str]
    review_field_keys: list[str]
    warnings: list[str]

@dataclass(frozen=True)
class RequirementEvidenceDraft:
    chunk_id: UUID
    logical_document_id: UUID
    page_id: UUID

    source_name: str
    page_number: int

    source_role: str
    binding_status: str
    precedence_order: int

    quote: str
    retrieval_score: float


@dataclass(frozen=True)
class RequirementDraft:
    requirement_code: str

    category_key: str
    category_label: str

    title: str
    requirement_text: str
    obligation_level: str

    condition_text: str | None
    bidder_proof: list[str]

    confidence: float
    needs_review: bool

    evidence: list[RequirementEvidenceDraft] = field(
        default_factory=list
    )
    warnings: list[str] = field(
        default_factory=list
    )


@dataclass(frozen=True)
class RequirementBuildResult:
    requirements: list[RequirementDraft]

    requirement_count: int
    mandatory_count: int
    conditional_count: int
    informational_count: int

    review_requirement_codes: list[str]
    warnings: list[str]


@dataclass(frozen=True)
class StoredRequirementEvidence:
    evidence_id: UUID
    chunk_id: UUID
    logical_document_id: UUID
    page_id: UUID

    source_role: str
    binding_status: str
    precedence_order: int

    quote: str


@dataclass(frozen=True)
class StoredRequirement:
    requirement_id: UUID
    requirement_code: str

    confidence: float
    extraction_needs_review: bool

    evidence: list[StoredRequirementEvidence] = field(
        default_factory=list
    )


@dataclass(frozen=True)
class EvidenceValidationDecision:
    evidence_id: UUID
    is_valid: bool
    validation_message: str


@dataclass(frozen=True)
class RequirementValidationDecision:
    requirement_id: UUID
    requirement_code: str

    validation_status: str
    needs_review: bool

    evidence_decisions: list[
        EvidenceValidationDecision
    ]
    warnings: list[str] = field(
        default_factory=list
    )


@dataclass(frozen=True)
class EvidenceValidationBuildResult:
    requirements: list[
        RequirementValidationDecision
    ]

    validated_count: int
    review_count: int
    invalid_count: int

    review_requirement_codes: list[str]
    invalid_requirement_codes: list[str]

    warnings: list[str]