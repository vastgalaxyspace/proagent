from __future__ import annotations

import operator
from typing import Annotated, Any, Literal

from typing_extensions import TypedDict


WorkflowStatus = Literal[
    "received",
    "loading",
    "inventorying",
    "validating",
    "extracting",
    "native_extracted",
    "quality_assessing",
    "quality_assessed",
    "selecting_base",
    "base_selected",
    "resolving_amendments",
    "amendments_resolved",
    "ocr_processing",
    "ocr_completed",
    "ready",
    "failed",
    "classifying",
    "classified",
    "structuring",
    "structured",
    "retrieving",
    "retrieval_indexed",
    "understanding_fields",
    "fields_understood",
    "normalizing",
    "normalized",
    "reconciling",
    "reconciled",
    "extracting_requirements",
    "requirements_extracted",
    "validating_requirement_evidence",
    "evidence_validated",
    "projecting_profile",
    "profile_projected",
    "auditing_coverage",
    "coverage_audited",
    "finally_validating",
    "finally_validated",
    "persisting",
    "persisted",
    "awaiting_review",
    "approved",
    "changes_requested",
    "rejected",
]


class TenderAgentState(TypedDict, total=False):
    request_id: str
    tender_id: str
    tender_version_id: str
    operation_id: str
    document_ids: list[str]

    owner_tenant_id: str
    started_by_user_id: str

    ingestion_verified: bool
    ingested_document_count: int
    ingested_total_bytes: int
    retrieval_index_completed: bool
    retrieval_index_id: str
    retrieval_chunk_count: int
    retrieval_indexed_page_count: int
    retrieval_skipped_page_count: int

    retrieval_embedding_provider: str
    retrieval_embedding_model: str
    retrieval_embedding_dimensions: int

    retrieval_reranker_provider: str
    retrieval_reranker_model: str

    profile_projection_completed: bool
    projected_field_count: int
    projected_requirement_count: int
    tender_profile: dict[str, Any]

    coverage_audit_completed: bool
    readiness_score: float
    coverage_issue_count: int
    coverage_warning_count: int
    coverage_error_count: int
    coverage_fatal_count: int
    coverage_audit: dict[str, Any]

    final_validation_completed: bool
    final_validation_status: str
    ready_for_review: bool
    review_reasons: list[str]
    final_validation: dict[str, Any]

    final_persistence_completed: bool
    finalization_run_id: str

    review_handoff_completed: bool
    review_session_id: str
    review_status: str
    review_decision: str
    review_comment: str | None
    review_correction_count: int
    reviewed_by_user_id: str
    tender_agent_completed: bool

    field_understanding_completed: bool
    field_understanding_run_id: str

    normalization_completed: bool
    normalization_run_id: str

    normalized_field_count: int
    unavailable_field_count: int
    normalization_candidate_count: int
    normalization_error_count: int

    normalization_review_field_keys: list[str]

    reconciliation_completed: bool
    reconciled_field_count: int
    conflict_field_count: int
    unresolved_field_count: int

    conflict_field_keys: list[str]
    reconciliation_review_field_keys: list[str]

    configured_field_count: int
    found_field_count: int
    not_found_field_count: int
    ambiguous_field_count: int
    field_error_count: int

    field_review_keys: list[str]

    base_selection_completed: bool
    source_plan_id: str
    primary_base_logical_document_id: str
    base_supporting_logical_document_ids: list[str]
    base_selection_confidence: float
    base_selection_needs_review: bool

    amendment_resolution_completed: bool
    effective_source_member_ids: list[str]
    effective_source_count: int
    binding_amendment_logical_document_ids: list[str]
    review_amendment_logical_document_ids: list[str]
    effective_source_needs_review: bool

    native_extraction_completed: bool
    extracted_document_ids: list[str]
    ocr_document_ids: list[str]
    empty_document_ids: list[str]
    failed_document_ids: list[str]
    extracted_page_count: int
    extracted_character_count: int

    classification_completed: bool
    classified_document_ids: list[str]
    classified_page_count: int
    classification_review_page_ids: list[str]
    document_type_counts: dict[str, int]
    post_base_document_ids: list[str]
    structure_completed: bool
    logical_document_ids: list[str]
    logical_document_count: int
    structured_page_count: int
    structure_review_logical_document_ids: list[str]
    logical_document_type_counts: dict[str, int]

    requirement_extraction_completed: bool
    requirement_run_id: str

    requirement_count: int
    mandatory_requirement_count: int
    conditional_requirement_count: int
    informational_requirement_count: int

    requirement_evidence_validated: bool
    validated_requirement_count: int
    review_requirement_count: int
    invalid_requirement_count: int

    requirement_review_codes: list[str]
    invalid_requirement_codes: list[str]

    quality_assessment_completed: bool
    quality_page_count: int
    quality_passed_page_ids: list[str]
    ocr_required_page_ids: list[str]

    ocr_recovery_completed: bool
    ocr_succeeded_page_ids: list[str]
    ocr_failed_page_ids: list[str]
    ocr_provider_name: str | None

    workflow_status: WorkflowStatus
    current_node: str
    next_action: str | None

    warnings: Annotated[list[str], operator.add]
    errors: Annotated[list[str], operator.add]

