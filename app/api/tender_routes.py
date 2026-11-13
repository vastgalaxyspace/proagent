from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID, uuid4
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from langgraph.types import Command


from app.api.dependencies import (
    RequestContext,
    get_database_session,
    get_coverage_service,
    get_evidence_service,
    get_classification_service,
    get_native_parser,
    get_normalization_service,
    get_ocr_provider,
    get_object_storage,
    get_quality_service,
    get_request_context,
    get_session_factory,
    get_tender_graph,
    get_structure_service,
    get_amendment_service,
    get_base_tender_service,
    get_field_catalog,
    get_retrieval_service,
    get_reconciliation_service,
    get_requirement_service,
    get_understanding_service,
    get_validation_service,
    get_handoff_service,
)
from app.tender_agent.handoff import HandoffService
from app.tender_agent.schemas.field_schema import (
    TenderFieldCatalog,
)
from app.tender_agent.services.structure_service import (
    StructureService,
)
from app.tender_agent.services.retrieval_service import (
    RetrievalService,
)
from app.tender_agent.services.understanding_service import (
    UnderstandingService,
)
from app.tender_agent.services.normalization_service import (
    NormalizationService,
)
from app.tender_agent.services.reconciliation_service import (
    ReconciliationService,
)
from app.tender_agent.services.evidence_service import (
    EvidenceService,
)
from app.tender_agent.services.requirement_service import (
    RequirementService,
)
from app.tender_agent.services.coverage_service import (
    CoverageService,
)
from app.tender_agent.services.validation_service import (
    ValidationService,
)
from app.tender_agent.services.amendment_service import (
    AmendmentService,
)
from app.tender_agent.services.base_tender_service import (
    BaseTenderService,
)
from app.core.config import get_settings
from app.infrastructure.providers.ocr import OCRProvider
from app.infrastructure.storage.interface import (
    ObjectStorage,
    ObjectStorageError,
)
from app.tender_agent.domain.exceptions import (
    InvalidUploadError,
    UploadTooLargeError,
)
from app.tender_agent.domain.statuses import OperationStatus
from app.tender_agent.repositories.audit_repository import AuditRepository
from app.tender_agent.repositories.document_repository import (
    DocumentRepository,
)
from app.tender_agent.repositories.operation_repository import (
    OperationRepository,
)
from app.tender_agent.repositories.review_repository import ReviewRepository
from app.tender_agent.schemas.review import (
    ReviewDecisionRequest,
    ReviewDecisionResponse,
    ReviewPackageResponse,
)
from app.tender_agent.repositories.tender_repository import TenderRepository
from app.tender_agent.schemas.responses import (
    RegisteredDocumentResponse,
    TenderCreatedResponse,
    TenderRunAccepted,
    TenderRunStatus,
)
from app.tender_agent.services.ingestion import (
    IngestionLimits,
    IngestionService,
)
from app.tender_agent.services.classification_service import (
    TenderClassificationService,
)
from app.tender_agent.services.native_parser import (
    NativeDocumentParser,
)
from app.tender_agent.services.quality_service import QualityService


router = APIRouter(
    prefix="/tenders",
    tags=["tender-agent"],
)


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=TenderCreatedResponse,
)
def create_tender(
    title: Annotated[
        str,
        Form(min_length=1, max_length=500),
    ],
    files: Annotated[
        list[UploadFile],
        File(),
    ],
    request_context: Annotated[
        RequestContext,
        Depends(get_request_context),
    ],
    session: Annotated[
        Session,
        Depends(get_database_session),
    ],
    storage: Annotated[
        ObjectStorage,
        Depends(get_object_storage),
    ],
    external_reference: Annotated[
        str | None,
        Form(max_length=255),
    ] = None,
) -> TenderCreatedResponse:
    settings = get_settings()

    ingestion_service = IngestionService(
        session=session,
        storage=storage,
        limits=IngestionLimits(
            max_files=settings.max_upload_files,
            max_file_bytes=settings.max_upload_file_bytes,
            max_total_bytes=settings.max_upload_total_bytes,
            chunk_bytes=settings.upload_chunk_bytes,
        ),
    )

    audit_repository = AuditRepository(session)
    ingestion_result = None

    try:
        ingestion_result = ingestion_service.ingest_tender(
            tenant_id=request_context.tenant_id,
            title=title,
            external_reference=external_reference,
            uploads=files,
        )

        tender = ingestion_result.tender
        version = ingestion_result.tender_version
        documents = ingestion_result.documents

        audit_repository.record(
            tenant_id=request_context.tenant_id,
            actor_user_id=request_context.user_id,
            event_type="tender.created",
            entity_type="tender",
            entity_id=str(tender.id),
            after={
                "tender_version_id": str(version.id),
                "documents": [
                    {
                        "document_id": str(document.id),
                        "file_name": document.file_name,
                        "size_bytes": document.size_bytes,
                        "sha256": document.sha256,
                    }
                    for document in documents
                ],
            },
        )

        session.commit()

    except UploadTooLargeError as exc:
        session.rollback()

        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=str(exc),
        ) from exc

    except InvalidUploadError as exc:
        session.rollback()

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    except IntegrityError as exc:
        session.rollback()

        if ingestion_result is not None:
            ingestion_service.cleanup_objects(
                ingestion_result.stored_object_keys
            )

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "A tender with this external reference "
                "already exists for the tenant."
            ),
        ) from exc

    except ObjectStorageError as exc:
        session.rollback()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="A tender document could not be stored.",
        ) from exc

    except Exception:
        session.rollback()

        if ingestion_result is not None:
            ingestion_service.cleanup_objects(
                ingestion_result.stored_object_keys
            )

        raise

    return TenderCreatedResponse(
        tender_id=tender.id,
        tender_version_id=version.id,
        title=tender.title,
        external_reference=tender.external_reference,
        status=tender.status,
        documents=[
            RegisteredDocumentResponse(
                document_id=document.id,
                file_name=document.file_name,
                content_type=document.content_type,
                size_bytes=document.size_bytes,
                sha256=document.sha256,
                storage_status=document.storage_status,
            )
            for document in documents
        ],
    )


@router.post(
    "/{tender_id}/runs",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=TenderRunAccepted,
)
def start_tender_run(
    tender_id: UUID,
    request: Request,
    request_context: Annotated[
        RequestContext,
        Depends(get_request_context),
    ],
    session: Annotated[
        Session,
        Depends(get_database_session),
    ],
    session_factory: Annotated[
        sessionmaker[Session],
        Depends(get_session_factory),
    ],
    graph: Annotated[
        Any,
        Depends(get_tender_graph),
    ],
    storage: Annotated[
        ObjectStorage,
        Depends(get_object_storage),
    ],
    native_parser: Annotated[
        NativeDocumentParser,
        Depends(get_native_parser),
    ],
    quality_service: Annotated[
        QualityService,
        Depends(get_quality_service),
    ],
    ocr_provider: Annotated[
        OCRProvider,
        Depends(get_ocr_provider),
    ],
    classification_service: Annotated[
        TenderClassificationService,
        Depends(get_classification_service),
    ],
    structure_service: Annotated[
        StructureService,
        Depends(get_structure_service),
    ],
    base_tender_service: Annotated[
        BaseTenderService,
        Depends(get_base_tender_service),
    ],
    amendment_service: Annotated[
        AmendmentService,
        Depends(get_amendment_service),
    ],
    retrieval_service: Annotated[
        RetrievalService,
        Depends(get_retrieval_service),
    ],
    field_catalog: Annotated[
        TenderFieldCatalog,
        Depends(get_field_catalog),
    ],
    understanding_service: Annotated[
        UnderstandingService,
        Depends(get_understanding_service),
    ],
    normalization_service: Annotated[
        NormalizationService,
        Depends(get_normalization_service),
    ],
    reconciliation_service: Annotated[
        ReconciliationService,
        Depends(get_reconciliation_service),
    ],
    requirement_service: Annotated[
        RequirementService,
        Depends(get_requirement_service),
    ],
    evidence_service: Annotated[
        EvidenceService,
        Depends(get_evidence_service),
    ],
    coverage_service: Annotated[
        CoverageService,
        Depends(get_coverage_service),
    ],
    validation_service: Annotated[
        ValidationService,
        Depends(get_validation_service),
    ],
    handoff_service: Annotated[
        HandoffService,
        Depends(get_handoff_service),
    ],
) -> TenderRunAccepted:
    settings = get_settings()
    tender_repository = TenderRepository(session)
    document_repository = DocumentRepository(session)
    operation_repository = OperationRepository(session)
    audit_repository = AuditRepository(session)

    tender = tender_repository.get_tender_for_tenant(
        tender_id=tender_id,
        tenant_id=request_context.tenant_id,
    )

    if tender is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tender was not found.",
        )

    version = tender_repository.get_current_version(
        tender_id=tender.id,
        tenant_id=request_context.tenant_id,
    )

    if version is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Tender has no active version.",
        )

    documents = document_repository.list_for_version(
        tender_version_id=version.id,
        tenant_id=request_context.tenant_id,
    )

    if not documents:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Tender has no registered documents.",
        )

    request_id = str(uuid4())

    thread_id = (
        f"tender:"
        f"{request_context.tenant_id}:"
        f"{version.id}:"
        f"{request_id}"
    )

    operation = operation_repository.create_operation(
        tenant_id=request_context.tenant_id,
        tender_version_id=version.id,
        request_id=request_id,
        thread_id=thread_id,
    )

    audit_repository.record(
        tenant_id=request_context.tenant_id,
        actor_user_id=request_context.user_id,
        event_type="tender.understanding.queued",
        entity_type="operation",
        entity_id=str(operation.id),
        after={
            "tender_id": str(tender.id),
            "tender_version_id": str(version.id),
            "thread_id": thread_id,
        },
    )

    operation_repository.mark_running(operation)
    session.commit()

    graph_config = {
        "configurable": {
            "thread_id": thread_id,
        }
    }

    initial_state = {
        "request_id": request_id,
        "tender_id": str(tender.id),
        "operation_id": str(operation.id),
        "warnings": [],
        "errors": [],
    }

    runtime_context = {
        "tenant_id": request_context.tenant_id,
        "user_id": request_context.user_id,
        "session_factory": session_factory,
        "object_storage": storage,
        "native_parser": native_parser,
        "quality_service": quality_service,
        "ocr_provider": ocr_provider,
        "structure_service": structure_service,
        "classification_service": classification_service,
        "base_tender_service": base_tender_service,
        "amendment_service": amendment_service,
        "ocr_max_attempts": settings.ocr_max_attempts,
        "retrieval_service": retrieval_service,
        "field_catalog": field_catalog,
        "understanding_service": understanding_service,
        "normalization_service": normalization_service,
        "reconciliation_service": reconciliation_service,
        "requirement_service": requirement_service,
        "evidence_service": evidence_service,
        "coverage_service": coverage_service,
        "validation_service": validation_service,
        "handoff_service": handoff_service,
        "thread_id": thread_id,
        "ocr_min_accepted_score": (
            settings.ocr_min_accepted_score
        ),
        "max_document_characters": (
            settings.max_document_characters
        ),
    }

    ai_providers = getattr(
        request.app.state,
        "ai_providers",
        None,
    )

    if ai_providers is not None:
        runtime_context["ai_providers"] = ai_providers

    try:
        result = graph.invoke(
            initial_state,
            config=graph_config,
            context=runtime_context,
        )

    except Exception as exc:
        operation_repository.mark_failed(
            operation,
            error_code="graph_execution_failed",
            error_detail=str(exc),
        )

        audit_repository.record(
            tenant_id=request_context.tenant_id,
            actor_user_id=request_context.user_id,
            event_type="tender.understanding.failed",
            entity_type="operation",
            entity_id=str(operation.id),
            after={
                "error_code": "graph_execution_failed",
            },
        )

        session.commit()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Tender Agent execution failed.",
        ) from exc

    result_summary = {
        "workflow_status": result.get("workflow_status"),
        "current_node": result.get("current_node"),
        "native_extraction_completed": result.get(
            "native_extraction_completed",
            False,
        ),
        "extracted_document_ids": result.get(
            "extracted_document_ids",
            [],
        ),
        "ocr_document_ids": result.get(
            "ocr_document_ids",
            [],
        ),
        "empty_document_ids": result.get(
            "empty_document_ids",
            [],
        ),
        "failed_document_ids": result.get(
            "failed_document_ids",
            [],
        ),
        "extracted_page_count": result.get(
            "extracted_page_count",
            0,
        ),
        "extracted_character_count": result.get(
            "extracted_character_count",
            0,
        ),
        "quality_assessment_completed": result.get(
            "quality_assessment_completed",
            False,
        ),
        "quality_page_count": result.get(
            "quality_page_count",
            0,
        ),
        "quality_passed_page_ids": result.get(
            "quality_passed_page_ids",
            [],
        ),
        "ocr_required_page_ids": result.get(
            "ocr_required_page_ids",
            [],
        ),
        "ocr_recovery_completed": result.get(
            "ocr_recovery_completed",
            False,
        ),
        "ocr_succeeded_page_ids": result.get(
            "ocr_succeeded_page_ids",
            [],
        ),
        "ocr_failed_page_ids": result.get(
            "ocr_failed_page_ids",
            [],
        ),
        "ocr_provider_name": result.get(
            "ocr_provider_name"
        ),
        "classification_completed": result.get(
            "classification_completed",
            False,
        ),
        "classified_document_ids": result.get(
            "classified_document_ids",
            [],
        ),
        "classified_page_count": result.get(
            "classified_page_count",
            0,
        ),
        "classification_review_page_ids": result.get(
            "classification_review_page_ids",
            [],
        ),
        "document_type_counts": result.get(
            "document_type_counts",
            {},
        ),
        "post_base_document_ids": result.get(
            "post_base_document_ids",
            [],
        ),
        "structure_completed": result.get(
            "structure_completed",
            False,
        ),
        "logical_document_ids": result.get(
            "logical_document_ids",
            [],
        ),
        "logical_document_count": result.get(
            "logical_document_count",
            0,
        ),
        "structured_page_count": result.get(
            "structured_page_count",
            0,
        ),
        "structure_review_logical_document_ids": result.get(
            "structure_review_logical_document_ids",
            [],
        ),
        "logical_document_type_counts": result.get(
            "logical_document_type_counts",
            {},
        ),
        "base_selection_completed": result.get(
            "base_selection_completed",
            False,
        ),
        "source_plan_id": result.get("source_plan_id"),
        "primary_base_logical_document_id": result.get(
            "primary_base_logical_document_id"
        ),
        "base_supporting_logical_document_ids": result.get(
            "base_supporting_logical_document_ids",
            [],
        ),
        "base_selection_confidence": result.get(
            "base_selection_confidence",
            0.0,
        ),
        "base_selection_needs_review": result.get(
            "base_selection_needs_review",
            False,
        ),
        "amendment_resolution_completed": result.get(
            "amendment_resolution_completed",
            False,
        ),
        "effective_source_member_ids": result.get(
            "effective_source_member_ids",
            [],
        ),
        "effective_source_count": result.get(
            "effective_source_count",
            0,
        ),
        "binding_amendment_logical_document_ids": result.get(
            "binding_amendment_logical_document_ids",
            [],
        ),
        "review_amendment_logical_document_ids": result.get(
            "review_amendment_logical_document_ids",
            [],
        ),
        "effective_source_needs_review": result.get(
            "effective_source_needs_review",
            False,
        ),
        "retrieval_index_completed": result.get(
            "retrieval_index_completed",
            False,
        ),
        "retrieval_index_id": result.get(
            "retrieval_index_id"
        ),
        "retrieval_chunk_count": result.get(
            "retrieval_chunk_count",
            0,
        ),
        "retrieval_indexed_page_count": result.get(
            "retrieval_indexed_page_count",
            0,
        ),
        "retrieval_skipped_page_count": result.get(
            "retrieval_skipped_page_count",
            0,
        ),
        "retrieval_embedding_provider": result.get(
            "retrieval_embedding_provider"
        ),
        "retrieval_embedding_model": result.get(
            "retrieval_embedding_model"
        ),
        "retrieval_embedding_dimensions": result.get(
            "retrieval_embedding_dimensions",
            0,
        ),
        "retrieval_reranker_provider": result.get(
            "retrieval_reranker_provider"
        ),
        "retrieval_reranker_model": result.get(
            "retrieval_reranker_model"
        ),
        "field_understanding_completed": result.get(
            "field_understanding_completed",
            False,
        ),
        "field_understanding_run_id": result.get(
            "field_understanding_run_id"
        ),
        "configured_field_count": result.get(
            "configured_field_count",
            0,
        ),
        "found_field_count": result.get(
            "found_field_count",
            0,
        ),
        "not_found_field_count": result.get(
            "not_found_field_count",
            0,
        ),
        "ambiguous_field_count": result.get(
            "ambiguous_field_count",
            0,
        ),
        "field_error_count": result.get(
            "field_error_count",
            0,
        ),
        "field_review_keys": result.get(
            "field_review_keys",
            [],
        ),
        "normalization_completed": result.get(
            "normalization_completed",
            False,
        ),
        "normalization_run_id": result.get(
            "normalization_run_id"
        ),
        "normalized_field_count": result.get(
            "normalized_field_count",
            0,
        ),
        "unavailable_field_count": result.get(
            "unavailable_field_count",
            0,
        ),
        "normalization_candidate_count": result.get(
            "normalization_candidate_count",
            0,
        ),
        "normalization_error_count": result.get(
            "normalization_error_count",
            0,
        ),
        "normalization_review_field_keys": result.get(
            "normalization_review_field_keys",
            [],
        ),
        "reconciliation_completed": result.get(
            "reconciliation_completed",
            False,
        ),
        "reconciled_field_count": result.get(
            "reconciled_field_count",
            0,
        ),
        "conflict_field_count": result.get(
            "conflict_field_count",
            0,
        ),
        "unresolved_field_count": result.get(
            "unresolved_field_count",
            0,
        ),
        "conflict_field_keys": result.get(
            "conflict_field_keys",
            [],
        ),
        "reconciliation_review_field_keys": result.get(
            "reconciliation_review_field_keys",
            [],
        ),
        "requirement_extraction_completed": result.get(
            "requirement_extraction_completed",
            False,
        ),
        "requirement_run_id": result.get(
            "requirement_run_id"
        ),
        "requirement_count": result.get(
            "requirement_count",
            0,
        ),
        "mandatory_requirement_count": result.get(
            "mandatory_requirement_count",
            0,
        ),
        "conditional_requirement_count": result.get(
            "conditional_requirement_count",
            0,
        ),
        "informational_requirement_count": result.get(
            "informational_requirement_count",
            0,
        ),
        "requirement_evidence_validated": result.get(
            "requirement_evidence_validated",
            False,
        ),
        "validated_requirement_count": result.get(
            "validated_requirement_count",
            0,
        ),
        "review_requirement_count": result.get(
            "review_requirement_count",
            0,
        ),
        "invalid_requirement_count": result.get(
            "invalid_requirement_count",
            0,
        ),
        "requirement_review_codes": result.get(
            "requirement_review_codes",
            [],
        ),
        "invalid_requirement_codes": result.get(
            "invalid_requirement_codes",
            [],
        ),
        "profile_projection_completed": result.get(
            "profile_projection_completed",
            False,
        ),
        "projected_field_count": result.get(
            "projected_field_count",
            0,
        ),
        "projected_requirement_count": result.get(
            "projected_requirement_count",
            0,
        ),
        "coverage_audit_completed": result.get(
            "coverage_audit_completed",
            False,
        ),
        "readiness_score": result.get(
            "readiness_score",
            0.0,
        ),
        "coverage_issue_count": result.get(
            "coverage_issue_count",
            0,
        ),
        "coverage_warning_count": result.get(
            "coverage_warning_count",
            0,
        ),
        "coverage_error_count": result.get(
            "coverage_error_count",
            0,
        ),
        "coverage_fatal_count": result.get(
            "coverage_fatal_count",
            0,
        ),
        "final_validation_completed": result.get(
            "final_validation_completed",
            False,
        ),
        "final_validation_status": result.get(
            "final_validation_status"
        ),
        "ready_for_review": result.get(
            "ready_for_review",
            False,
        ),
        "review_reasons": result.get(
            "review_reasons",
            [],
        ),
        "final_persistence_completed": result.get(
            "final_persistence_completed",
            False,
        ),
        "finalization_run_id": result.get(
            "finalization_run_id"
        ),
        "warnings": result.get("warnings", []),
        "errors": result.get("errors", []),
    }

    interrupted = bool(result.get("__interrupt__"))

    if result.get("workflow_status") == "failed":
        operation_repository.mark_failed(
            operation,
            error_code="graph_validation_failed",
            error_detail="Tender Agent validation failed.",
            result=result_summary,
        )

        event_type = "tender.understanding.failed"
    elif interrupted:
        result_summary["workflow_status"] = "awaiting_review"
        result_summary["current_node"] = "review_handoff"
        operation_repository.mark_awaiting_review(
            operation,
            result=result_summary,
        )
        event_type = "tender.review.awaiting"
    else:
        operation_repository.mark_succeeded(
            operation,
            result=result_summary,
        )

        event_type = "tender.understanding.succeeded"

    audit_repository.record(
        tenant_id=request_context.tenant_id,
        actor_user_id=request_context.user_id,
        event_type=event_type,
        entity_type="operation",
        entity_id=str(operation.id),
        after=result_summary,
    )

    session.commit()

    status_url = str(
        request.url_for(
            "get_tender_run_status",
            thread_id=thread_id,
        )
    )

    return TenderRunAccepted(
        operation_id=operation.id,
        thread_id=thread_id,
        request_id=request_id,
        workflow_status=result_summary.get("workflow_status", "failed"),
        status_url=status_url,
    )


@router.get(
    "/runs/{thread_id}/review",
    response_model=ReviewPackageResponse,
)
def get_tender_review(
    thread_id: str,
    request_context: Annotated[RequestContext, Depends(get_request_context)],
    session: Annotated[Session, Depends(get_database_session)],
) -> ReviewPackageResponse:
    repository = ReviewRepository(session)
    review = repository.get_by_thread(
        thread_id=thread_id,
        tenant_id=request_context.tenant_id,
    )
    if review is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tender review session was not found.",
        )
    return ReviewPackageResponse(
        review_session_id=review.id,
        thread_id=review.thread_id,
        finalization_run_id=review.finalization_run_id,
        tender_version_id=review.tender_version_id,
        status=review.status,
        package=review.package_json,
        corrected_profile=review.corrected_profile_json,
        corrections=[
            {
                "target_type": correction.target_type,
                "target_key": correction.target_key,
                "patch": correction.patch_json,
                "reason": correction.reason,
            }
            for correction in repository.list_corrections(
                review_session_id=review.id
            )
        ],
        decision=review.decision,
        comment=review.comment,
        correction_count=review.correction_count,
        reviewer_user_id=review.reviewer_user_id,
    )


@router.post(
    "/runs/{thread_id}/review",
    response_model=ReviewDecisionResponse,
)
def decide_tender_review(
    thread_id: str,
    decision: ReviewDecisionRequest,
    request_context: Annotated[RequestContext, Depends(get_request_context)],
    session: Annotated[Session, Depends(get_database_session)],
    session_factory: Annotated[sessionmaker[Session], Depends(get_session_factory)],
    graph: Annotated[Any, Depends(get_tender_graph)],
    handoff_service: Annotated[HandoffService, Depends(get_handoff_service)],
) -> ReviewDecisionResponse:
    operation_repository = OperationRepository(session)
    operation = operation_repository.get_by_thread(
        thread_id=thread_id,
        tenant_id=request_context.tenant_id,
    )
    review_repository = ReviewRepository(session)
    review = review_repository.get_by_thread(
        thread_id=thread_id,
        tenant_id=request_context.tenant_id,
    )
    if operation is None or review is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tender review session was not found.",
        )
    if operation.status != OperationStatus.AWAITING_REVIEW.value or review.status != "awaiting_review":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Tender review is not awaiting a decision.",
        )

    try:
        handoff_service.apply_corrections(
            profile=review.package_json["profile"],
            corrections=decision.corrections,
        )
    except (KeyError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    resume_payload = {
        **decision.model_dump(mode="json"),
        "reviewer_user_id": request_context.user_id,
    }
    graph_config = {"configurable": {"thread_id": thread_id}}
    runtime_context = {
        "tenant_id": request_context.tenant_id,
        "user_id": request_context.user_id,
        "session_factory": session_factory,
        "handoff_service": handoff_service,
        "thread_id": thread_id,
    }
    try:
        result = graph.invoke(
            Command(resume=resume_payload),
            config=graph_config,
            context=runtime_context,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Tender review resume failed.",
        ) from exc

    result_summary = dict(operation.result_json or {})
    result_summary.update(
        {
            "workflow_status": result.get("workflow_status", decision.decision),
            "current_node": result.get("current_node", "review_handoff"),
            "review_handoff_completed": result.get("review_handoff_completed", True),
            "review_session_id": result.get("review_session_id", str(review.id)),
            "review_status": decision.decision,
            "review_decision": decision.decision,
            "review_comment": decision.comment,
            "review_correction_count": len(decision.corrections),
            "reviewed_by_user_id": request_context.user_id,
            "tender_agent_completed": True,
        }
    )
    operation_repository.mark_review_completed(
        operation,
        decision=decision.decision,
        result=result_summary,
    )
    session.commit()

    return ReviewDecisionResponse(
        review_session_id=review.id,
        thread_id=thread_id,
        status=decision.decision,
        workflow_status=result_summary["workflow_status"],
        correction_count=len(decision.corrections),
        completed=True,
    )


@router.get(
    "/runs/{thread_id}",
    response_model=TenderRunStatus,
    name="get_tender_run_status",
)
def get_tender_run_status(
    thread_id: str,
    request_context: Annotated[
        RequestContext,
        Depends(get_request_context),
    ],
    session: Annotated[
        Session,
        Depends(get_database_session),
    ],
    graph: Annotated[
        Any,
        Depends(get_tender_graph),
    ],
) -> TenderRunStatus:
    operation_repository = OperationRepository(session)
    document_repository = DocumentRepository(session)
    review_repository = ReviewRepository(session)

    operation = operation_repository.get_by_thread(
        thread_id=thread_id,
        tenant_id=request_context.tenant_id,
    )

    if operation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tender Agent run was not found.",
        )

    graph_config = {
        "configurable": {
            "thread_id": thread_id,
        }
    }

    snapshot = graph.get_state(graph_config)
    state = snapshot.values or {}

    documents = document_repository.list_for_version(
        tender_version_id=operation.tender_version_id,
        tenant_id=request_context.tenant_id,
    )

    persisted_result = operation.result_json or {}
    review = review_repository.get_by_thread(
        thread_id=thread_id,
        tenant_id=request_context.tenant_id,
    )

    operation_complete = operation.status in {
        OperationStatus.SUCCEEDED.value,
        OperationStatus.FAILED.value,
        OperationStatus.APPROVED.value,
        OperationStatus.CHANGES_REQUESTED.value,
        OperationStatus.REJECTED.value,
    }

    return TenderRunStatus(
        operation_id=operation.id,
        thread_id=operation.thread_id,
        request_id=operation.request_id,
        tender_version_id=operation.tender_version_id,
        document_ids=(
            state.get("document_ids")
            or [str(document.id) for document in documents]
        ),
        retrieval_index_completed=(
            state.get("retrieval_index_completed")
            if state.get("retrieval_index_completed")
            is not None
            else persisted_result.get(
                "retrieval_index_completed",
                False,
            )
        ),
        retrieval_index_id=(
            state.get("retrieval_index_id")
            or persisted_result.get("retrieval_index_id")
        ),
        retrieval_chunk_count=(
            state.get("retrieval_chunk_count")
            if state.get("retrieval_chunk_count") is not None
            else persisted_result.get(
                "retrieval_chunk_count",
                0,
            )
        ),
        retrieval_indexed_page_count=(
            state.get("retrieval_indexed_page_count")
            if state.get("retrieval_indexed_page_count")
            is not None
            else persisted_result.get(
                "retrieval_indexed_page_count",
                0,
            )
        ),
        retrieval_skipped_page_count=(
            state.get("retrieval_skipped_page_count")
            if state.get("retrieval_skipped_page_count")
            is not None
            else persisted_result.get(
                "retrieval_skipped_page_count",
                0,
            )
        ),
        retrieval_embedding_provider=(
            state.get("retrieval_embedding_provider")
            or persisted_result.get(
                "retrieval_embedding_provider"
            )
        ),
        retrieval_embedding_model=(
            state.get("retrieval_embedding_model")
            or persisted_result.get(
                "retrieval_embedding_model"
            )
        ),
        retrieval_embedding_dimensions=(
            state.get("retrieval_embedding_dimensions")
            if state.get("retrieval_embedding_dimensions")
            is not None
            else persisted_result.get(
                "retrieval_embedding_dimensions",
                0,
            )
        ),
        retrieval_reranker_provider=(
            state.get("retrieval_reranker_provider")
            or persisted_result.get(
                "retrieval_reranker_provider"
            )
        ),
        retrieval_reranker_model=(
            state.get("retrieval_reranker_model")
            or persisted_result.get(
                "retrieval_reranker_model"
            )
        ),
        field_understanding_completed=(
            state.get("field_understanding_completed")
            if state.get("field_understanding_completed")
            is not None
            else persisted_result.get(
                "field_understanding_completed",
                False,
            )
        ),
        field_understanding_run_id=(
            state.get("field_understanding_run_id")
            or persisted_result.get(
                "field_understanding_run_id"
            )
        ),
        configured_field_count=(
            state.get("configured_field_count")
            if state.get("configured_field_count") is not None
            else persisted_result.get(
                "configured_field_count",
                0,
            )
        ),
        found_field_count=(
            state.get("found_field_count")
            if state.get("found_field_count") is not None
            else persisted_result.get(
                "found_field_count",
                0,
            )
        ),
        not_found_field_count=(
            state.get("not_found_field_count")
            if state.get("not_found_field_count") is not None
            else persisted_result.get(
                "not_found_field_count",
                0,
            )
        ),
        ambiguous_field_count=(
            state.get("ambiguous_field_count")
            if state.get("ambiguous_field_count") is not None
            else persisted_result.get(
                "ambiguous_field_count",
                0,
            )
        ),
        field_error_count=(
            state.get("field_error_count")
            if state.get("field_error_count") is not None
            else persisted_result.get(
                "field_error_count",
                0,
            )
        ),
        field_review_keys=(
            state.get("field_review_keys")
            or persisted_result.get("field_review_keys", [])
        ),
        normalization_completed=(
            state.get("normalization_completed")
            if state.get("normalization_completed") is not None
            else persisted_result.get(
                "normalization_completed",
                False,
            )
        ),
        normalization_run_id=(
            state.get("normalization_run_id")
            or persisted_result.get("normalization_run_id")
        ),
        normalized_field_count=(
            state.get("normalized_field_count")
            if state.get("normalized_field_count") is not None
            else persisted_result.get(
                "normalized_field_count",
                0,
            )
        ),
        unavailable_field_count=(
            state.get("unavailable_field_count")
            if state.get("unavailable_field_count") is not None
            else persisted_result.get(
                "unavailable_field_count",
                0,
            )
        ),
        normalization_candidate_count=(
            state.get("normalization_candidate_count")
            if state.get("normalization_candidate_count") is not None
            else persisted_result.get(
                "normalization_candidate_count",
                0,
            )
        ),
        normalization_error_count=(
            state.get("normalization_error_count")
            if state.get("normalization_error_count") is not None
            else persisted_result.get(
                "normalization_error_count",
                0,
            )
        ),
        normalization_review_field_keys=(
            state.get("normalization_review_field_keys")
            or persisted_result.get(
                "normalization_review_field_keys",
                [],
            )
        ),
        reconciliation_completed=(
            state.get("reconciliation_completed")
            if state.get("reconciliation_completed") is not None
            else persisted_result.get(
                "reconciliation_completed",
                False,
            )
        ),
        reconciled_field_count=(
            state.get("reconciled_field_count")
            if state.get("reconciled_field_count") is not None
            else persisted_result.get(
                "reconciled_field_count",
                0,
            )
        ),
        conflict_field_count=(
            state.get("conflict_field_count")
            if state.get("conflict_field_count") is not None
            else persisted_result.get(
                "conflict_field_count",
                0,
            )
        ),
        unresolved_field_count=(
            state.get("unresolved_field_count")
            if state.get("unresolved_field_count") is not None
            else persisted_result.get(
                "unresolved_field_count",
                0,
            )
        ),
        conflict_field_keys=(
            state.get("conflict_field_keys")
            or persisted_result.get("conflict_field_keys", [])
        ),
        reconciliation_review_field_keys=(
            state.get("reconciliation_review_field_keys")
            or persisted_result.get(
                "reconciliation_review_field_keys",
                [],
            )
        ),
        requirement_extraction_completed=(
            state.get(
                "requirement_extraction_completed"
            )
            if state.get(
                "requirement_extraction_completed"
            ) is not None
            else persisted_result.get(
                "requirement_extraction_completed",
                False,
            )
        ),
        requirement_run_id=(
            state.get("requirement_run_id")
            or persisted_result.get(
                "requirement_run_id"
            )
        ),
        requirement_count=(
            state.get("requirement_count")
            if state.get("requirement_count") is not None
            else persisted_result.get(
                "requirement_count",
                0,
            )
        ),
        mandatory_requirement_count=(
            state.get("mandatory_requirement_count")
            if state.get("mandatory_requirement_count")
            is not None
            else persisted_result.get(
                "mandatory_requirement_count",
                0,
            )
        ),
        conditional_requirement_count=(
            state.get("conditional_requirement_count")
            if state.get("conditional_requirement_count")
            is not None
            else persisted_result.get(
                "conditional_requirement_count",
                0,
            )
        ),
        informational_requirement_count=(
            state.get(
                "informational_requirement_count"
            )
            if state.get(
                "informational_requirement_count"
            ) is not None
            else persisted_result.get(
                "informational_requirement_count",
                0,
            )
        ),
        requirement_evidence_validated=(
            state.get("requirement_evidence_validated")
            if state.get(
                "requirement_evidence_validated"
            ) is not None
            else persisted_result.get(
                "requirement_evidence_validated",
                False,
            )
        ),
        validated_requirement_count=(
            state.get("validated_requirement_count")
            if state.get("validated_requirement_count")
            is not None
            else persisted_result.get(
                "validated_requirement_count",
                0,
            )
        ),
        review_requirement_count=(
            state.get("review_requirement_count")
            if state.get("review_requirement_count")
            is not None
            else persisted_result.get(
                "review_requirement_count",
                0,
            )
        ),
        invalid_requirement_count=(
            state.get("invalid_requirement_count")
            if state.get("invalid_requirement_count")
            is not None
            else persisted_result.get(
                "invalid_requirement_count",
                0,
            )
        ),
        requirement_review_codes=(
            state.get("requirement_review_codes")
            or persisted_result.get(
                "requirement_review_codes",
                [],
            )
        ),
        invalid_requirement_codes=(
            state.get("invalid_requirement_codes")
            or persisted_result.get(
                "invalid_requirement_codes",
                [],
            )
        ),
        profile_projection_completed=(
            state.get("profile_projection_completed")
            if state.get("profile_projection_completed")
            is not None
            else persisted_result.get(
                "profile_projection_completed",
                False,
            )
        ),
        projected_field_count=(
            state.get("projected_field_count")
            if state.get("projected_field_count")
            is not None
            else persisted_result.get(
                "projected_field_count",
                0,
            )
        ),
        projected_requirement_count=(
            state.get("projected_requirement_count")
            if state.get("projected_requirement_count")
            is not None
            else persisted_result.get(
                "projected_requirement_count",
                0,
            )
        ),
        coverage_audit_completed=(
            state.get("coverage_audit_completed")
            if state.get("coverage_audit_completed")
            is not None
            else persisted_result.get(
                "coverage_audit_completed",
                False,
            )
        ),
        readiness_score=(
            state.get("readiness_score")
            if state.get("readiness_score") is not None
            else persisted_result.get(
                "readiness_score",
                0.0,
            )
        ),
        coverage_issue_count=(
            state.get("coverage_issue_count")
            if state.get("coverage_issue_count") is not None
            else persisted_result.get(
                "coverage_issue_count",
                0,
            )
        ),
        coverage_warning_count=(
            state.get("coverage_warning_count")
            if state.get("coverage_warning_count") is not None
            else persisted_result.get(
                "coverage_warning_count",
                0,
            )
        ),
        coverage_error_count=(
            state.get("coverage_error_count")
            if state.get("coverage_error_count") is not None
            else persisted_result.get(
                "coverage_error_count",
                0,
            )
        ),
        coverage_fatal_count=(
            state.get("coverage_fatal_count")
            if state.get("coverage_fatal_count") is not None
            else persisted_result.get(
                "coverage_fatal_count",
                0,
            )
        ),
        final_validation_completed=(
            state.get("final_validation_completed")
            if state.get("final_validation_completed")
            is not None
            else persisted_result.get(
                "final_validation_completed",
                False,
            )
        ),
        final_validation_status=(
            state.get("final_validation_status")
            or persisted_result.get(
                "final_validation_status"
            )
        ),
        ready_for_review=(
            state.get("ready_for_review")
            if state.get("ready_for_review") is not None
            else persisted_result.get(
                "ready_for_review",
                False,
            )
        ),
        review_reasons=(
            state.get("review_reasons")
            or persisted_result.get(
                "review_reasons",
                [],
            )
        ),
        final_persistence_completed=(
            state.get("final_persistence_completed")
            if state.get("final_persistence_completed")
            is not None
            else persisted_result.get(
                "final_persistence_completed",
                False,
            )
        ),
        finalization_run_id=(
            state.get("finalization_run_id")
            or persisted_result.get(
                "finalization_run_id"
            )
        ),
        review_handoff_completed=(
            state.get("review_handoff_completed")
            or persisted_result.get("review_handoff_completed", False)
        ),
        review_session_id=(
            state.get("review_session_id")
            or persisted_result.get("review_session_id")
            or (str(review.id) if review is not None else None)
        ),
        review_status=(
            state.get("review_status")
            or persisted_result.get("review_status")
            or (review.status if review is not None else None)
        ),
        review_decision=(
            state.get("review_decision")
            or persisted_result.get("review_decision")
            or (review.decision if review is not None else None)
        ),
        review_comment=(
            state.get("review_comment")
            or persisted_result.get("review_comment")
            or (review.comment if review is not None else None)
        ),
        review_correction_count=(
            state.get("review_correction_count")
            if state.get("review_correction_count") is not None
            else persisted_result.get(
                "review_correction_count",
                review.correction_count if review is not None else 0,
            )
        ),
        reviewed_by_user_id=(
            state.get("reviewed_by_user_id")
            or persisted_result.get("reviewed_by_user_id")
            or (review.reviewer_user_id if review is not None else None)
        ),
        tender_agent_completed=(
            state.get("tender_agent_completed")
            or persisted_result.get("tender_agent_completed", False)
        ),
        operation_status=operation.status,
        workflow_status=(
            operation.status
            if operation.status in {
                OperationStatus.AWAITING_REVIEW.value,
                OperationStatus.APPROVED.value,
                OperationStatus.CHANGES_REQUESTED.value,
                OperationStatus.REJECTED.value,
            }
            else state.get("workflow_status")
            or persisted_result.get("workflow_status")
            or operation.status
        ),
        current_node=(
            "review_handoff"
            if operation.status
            == OperationStatus.AWAITING_REVIEW.value
            else state.get("current_node")
            or persisted_result.get("current_node")
        ),
        next_action=state.get("next_action"),
        next_nodes=list(snapshot.next),
        native_extraction_completed=(
            state.get("native_extraction_completed")
            or persisted_result.get(
                "native_extraction_completed",
                False,
            )
        ),
        quality_assessment_completed=(
            state.get("quality_assessment_completed")
            or persisted_result.get(
                "quality_assessment_completed",
                False,
            )
        ),
        quality_page_count=(
            state.get("quality_page_count")
            or persisted_result.get("quality_page_count", 0)
        ),
        quality_passed_page_ids=(
            state.get("quality_passed_page_ids")
            or persisted_result.get(
                "quality_passed_page_ids",
                [],
            )
        ),
        ocr_required_page_ids=(
            state.get("ocr_required_page_ids")
            or persisted_result.get(
                "ocr_required_page_ids",
                [],
            )
        ),
        ocr_recovery_completed=(
            state.get("ocr_recovery_completed")
            or persisted_result.get(
                "ocr_recovery_completed",
                False,
            )
        ),
        ocr_succeeded_page_ids=(
            state.get("ocr_succeeded_page_ids")
            or persisted_result.get(
                "ocr_succeeded_page_ids",
                [],
            )
        ),
        ocr_failed_page_ids=(
            state.get("ocr_failed_page_ids")
            or persisted_result.get(
                "ocr_failed_page_ids",
                [],
            )
        ),
        ocr_provider_name=(
            state.get("ocr_provider_name")
            or persisted_result.get("ocr_provider_name")
        ),
        classification_completed=(
            state.get("classification_completed")
            or persisted_result.get(
                "classification_completed",
                False,
            )
        ),
        classified_document_ids=(
            state.get("classified_document_ids")
            or persisted_result.get(
                "classified_document_ids",
                [],
            )
        ),
        classified_page_count=(
            state.get("classified_page_count")
            or persisted_result.get(
                "classified_page_count",
                0,
            )
        ),
        classification_review_page_ids=(
            state.get("classification_review_page_ids")
            or persisted_result.get(
                "classification_review_page_ids",
                [],
            )
        ),
        document_type_counts=(
            state.get("document_type_counts")
            or persisted_result.get(
                "document_type_counts",
                {},
            )
        ),
        post_base_document_ids=(
            state.get("post_base_document_ids")
            or persisted_result.get(
                "post_base_document_ids",
                [],
            )
        ),
        structure_completed=(
            state.get("structure_completed")
            or persisted_result.get(
                "structure_completed",
                False,
            )
        ),
        logical_document_ids=(
            state.get("logical_document_ids")
            or persisted_result.get(
                "logical_document_ids",
                [],
            )
        ),
        logical_document_count=(
            state.get("logical_document_count")
            or persisted_result.get(
                "logical_document_count",
                0,
            )
        ),
        structured_page_count=(
            state.get("structured_page_count")
            or persisted_result.get(
                "structured_page_count",
                0,
            )
        ),
        structure_review_logical_document_ids=(
            state.get(
                "structure_review_logical_document_ids"
            )
            or persisted_result.get(
                "structure_review_logical_document_ids",
                [],
            )
        ),
        logical_document_type_counts=(
            state.get("logical_document_type_counts")
            or persisted_result.get(
                "logical_document_type_counts",
                {},
            )
        ),
        base_selection_completed=(
            state.get("base_selection_completed")
            or persisted_result.get(
                "base_selection_completed",
                False,
            )
        ),
        source_plan_id=(
            state.get("source_plan_id")
            or persisted_result.get("source_plan_id")
        ),
        primary_base_logical_document_id=(
            state.get("primary_base_logical_document_id")
            or persisted_result.get(
                "primary_base_logical_document_id"
            )
        ),
        base_supporting_logical_document_ids=(
            state.get("base_supporting_logical_document_ids")
            or persisted_result.get(
                "base_supporting_logical_document_ids",
                [],
            )
        ),
        base_selection_confidence=(
            state.get("base_selection_confidence")
            if state.get("base_selection_confidence") is not None
            else persisted_result.get(
                "base_selection_confidence",
                0.0,
            )
        ),
        base_selection_needs_review=(
            state.get("base_selection_needs_review")
            if state.get("base_selection_needs_review") is not None
            else persisted_result.get(
                "base_selection_needs_review",
                False,
            )
        ),
        amendment_resolution_completed=(
            state.get("amendment_resolution_completed")
            or persisted_result.get(
                "amendment_resolution_completed",
                False,
            )
        ),
        effective_source_member_ids=(
            state.get("effective_source_member_ids")
            or persisted_result.get(
                "effective_source_member_ids",
                [],
            )
        ),
        effective_source_count=(
            state.get("effective_source_count")
            if state.get("effective_source_count") is not None
            else persisted_result.get(
                "effective_source_count",
                0,
            )
        ),
        binding_amendment_logical_document_ids=(
            state.get(
                "binding_amendment_logical_document_ids"
            )
            or persisted_result.get(
                "binding_amendment_logical_document_ids",
                [],
            )
        ),
        review_amendment_logical_document_ids=(
            state.get(
                "review_amendment_logical_document_ids"
            )
            or persisted_result.get(
                "review_amendment_logical_document_ids",
                [],
            )
        ),
        effective_source_needs_review=(
            state.get("effective_source_needs_review")
            if state.get("effective_source_needs_review") is not None
            else persisted_result.get(
                "effective_source_needs_review",
                False,
            )
        ),
        completed=operation_complete,
        warnings=(
            state.get("warnings")
            or persisted_result.get("warnings")
            or []
        ),
        errors=(
            state.get("errors")
            or persisted_result.get("errors")
            or []
        ),
        error_code=operation.error_code,
        error_detail=operation.error_detail,
    )
