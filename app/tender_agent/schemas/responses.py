from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str
    application: str
    environment: str


class ReadinessResponse(BaseModel):
    status: str
    database: str
    checkpoint_store: str
    object_storage: str
    ocr_provider: str
    ocr_available: bool
    ocr_model: str | None = None
    ai_enabled: bool = False
    ai_provider: str | None = None
    main_llm_model: str | None = None
    verifier_model: str | None = None
    embedding_model: str | None = None
    reranker_model: str | None = None


class RegisteredDocumentResponse(BaseModel):
    document_id: UUID
    file_name: str
    content_type: str | None
    size_bytes: int | None
    sha256: str | None
    storage_status: str


class TenderCreatedResponse(BaseModel):
    tender_id: UUID
    tender_version_id: UUID
    title: str
    external_reference: str | None
    status: str
    documents: list[RegisteredDocumentResponse]


class TenderRunAccepted(BaseModel):
    operation_id: UUID
    thread_id: str
    request_id: str
    workflow_status: str
    status_url: str


class RunControlResponse(BaseModel):
    operation_id: UUID
    thread_id: str
    operation_status: str
    message: str


class TenderRunStatus(BaseModel):
    operation_id: UUID
    thread_id: str
    request_id: str
    tender_version_id: UUID
    heartbeat_at: datetime | None = None
    pause_requested_at: datetime | None = None
    cancel_requested_at: datetime | None = None
    control_message: str | None = None
    document_ids: list[str]
    completed_nodes: list[str] = Field(
        default_factory=list
    )
    skipped_nodes: list[str] = Field(
        default_factory=list
    )
    failed_node: str | None = None
    node_events: list[dict[str, Any]] = Field(
        default_factory=list
    )
    retrieval_index_completed: bool = False
    retrieval_index_id: str | None = None
    retrieval_chunk_count: int = 0
    retrieval_indexed_page_count: int = 0
    retrieval_skipped_page_count: int = 0

    retrieval_embedding_provider: str | None = None
    retrieval_embedding_model: str | None = None
    retrieval_embedding_dimensions: int = 0

    retrieval_reranker_provider: str | None = None
    retrieval_reranker_model: str | None = None

    normalization_completed: bool = False
    normalization_run_id: str | None = None

    normalized_field_count: int = 0
    unavailable_field_count: int = 0
    normalization_candidate_count: int = 0
    normalization_error_count: int = 0

    normalization_review_field_keys: list[str] = Field(
        default_factory=list
    )

    reconciliation_completed: bool = False
    reconciled_field_count: int = 0
    conflict_field_count: int = 0
    unresolved_field_count: int = 0

    requirement_extraction_completed: bool = False
    requirement_run_id: str | None = None

    requirement_count: int = 0
    mandatory_requirement_count: int = 0
    conditional_requirement_count: int = 0
    informational_requirement_count: int = 0

    requirement_evidence_validated: bool = False
    validated_requirement_count: int = 0
    review_requirement_count: int = 0
    invalid_requirement_count: int = 0

    requirement_review_codes: list[str] = Field(
        default_factory=list
    )
    invalid_requirement_codes: list[str] = Field(
        default_factory=list
    )

    profile_projection_completed: bool = False
    projected_field_count: int = 0
    projected_requirement_count: int = 0

    coverage_audit_completed: bool = False
    readiness_score: float = 0.0
    coverage_issue_count: int = 0
    coverage_warning_count: int = 0
    coverage_error_count: int = 0
    coverage_fatal_count: int = 0

    final_validation_completed: bool = False
    final_validation_status: str | None = None
    ready_for_review: bool = False
    review_reasons: list[str] = Field(
        default_factory=list
    )

    final_persistence_completed: bool = False
    finalization_run_id: str | None = None

    review_handoff_completed: bool = False
    review_session_id: str | None = None
    review_status: str | None = None
    review_decision: str | None = None
    review_comment: str | None = None
    review_correction_count: int = 0
    reviewed_by_user_id: str | None = None
    tender_agent_completed: bool = False

    conflict_field_keys: list[str] = Field(
        default_factory=list
    )

    reconciliation_review_field_keys: list[str] = Field(
        default_factory=list
    )

    field_understanding_completed: bool = False
    field_understanding_run_id: str | None = None
    configured_field_count: int = 0
    found_field_count: int = 0
    not_found_field_count: int = 0
    ambiguous_field_count: int = 0
    field_error_count: int = 0
    field_review_keys: list[str] = Field(
        default_factory=list
    )

    operation_status: str
    workflow_status: str

    current_node: str | None = None
    next_action: str | None = None
    next_nodes: list[str] = Field(default_factory=list)

    native_extraction_completed: bool = False

    quality_assessment_completed: bool = False
    quality_page_count: int = 0
    quality_passed_page_ids: list[str] = Field(
        default_factory=list
    )

    ocr_required_page_ids: list[str] = Field(
        default_factory=list
    )
    ocr_recovery_completed: bool = False
    ocr_succeeded_page_ids: list[str] = Field(
        default_factory=list
    )
    ocr_failed_page_ids: list[str] = Field(
        default_factory=list
    )
    ocr_provider_name: str | None = None

    classification_completed: bool = False
    classified_document_ids: list[str] = Field(
        default_factory=list
    )
    classified_page_count: int = 0
    classification_review_page_ids: list[str] = Field(
        default_factory=list
    )
    document_type_counts: dict[str, int] = Field(
        default_factory=dict
    )
    post_base_document_ids: list[str] = Field(
        default_factory=list
    )

    structure_completed: bool = False
    logical_document_ids: list[str] = Field(
        default_factory=list
    )
    logical_document_count: int = 0
    structured_page_count: int = 0
    structure_review_logical_document_ids: list[str] = Field(
        default_factory=list
    )
    logical_document_type_counts: dict[str, int] = Field(
        default_factory=dict
    )

    base_selection_completed: bool = False
    source_plan_id: str | None = None
    primary_base_logical_document_id: str | None = None
    base_supporting_logical_document_ids: list[str] = Field(
        default_factory=list
    )
    authoritative_logical_document_ids: list[str] = Field(
        default_factory=list
    )
    excluded_reference_logical_document_ids: list[str] = Field(
        default_factory=list
    )
    base_selection_confidence: float = 0.0
    base_selection_needs_review: bool = False

    amendment_resolution_completed: bool = False
    effective_source_member_ids: list[str] = Field(
        default_factory=list
    )
    effective_source_count: int = 0
    binding_amendment_logical_document_ids: list[str] = Field(
        default_factory=list
    )
    review_amendment_logical_document_ids: list[str] = Field(
        default_factory=list
    )
    effective_source_needs_review: bool = False
    amendment_operation_count: int = 0
    validated_amendment_operation_count: int = 0
    review_amendment_operation_count: int = 0
    amendment_operations: list[dict[str, Any]] = Field(
        default_factory=list
    )

    completed: bool
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)

    error_code: str | None = None
    error_detail: str | None = None
