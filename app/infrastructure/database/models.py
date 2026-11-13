from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base
from app.tender_agent.domain.statuses import (
    DocumentExtractionStatus,
    DocumentStorageStatus,
    OperationStatus,
    TenderStatus,
    TenderVersionStatus,
)


class Tender(Base):
    __tablename__ = "tenders"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "external_reference",
            name="uq_tenders_tenant_external_reference",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    tenant_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )

    external_reference: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    title: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=TenderStatus.DRAFT.value,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class TenderVersion(Base):
    __tablename__ = "tender_versions"
    __table_args__ = (
        UniqueConstraint(
            "tender_id",
            "version_number",
            name="uq_tender_versions_tender_number",
        ),
        Index(
            "ix_tender_versions_tender_status",
            "tender_id",
            "status",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    tender_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    version_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=TenderVersionStatus.DRAFT.value,
    )

    understanding_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        Index(
            "ix_documents_version_storage",
            "tender_version_id",
            "storage_status",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    tenant_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )

    tender_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("tender_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    file_name: Mapped[str] = mapped_column(
        String(512),
        nullable=False,
    )

    content_type: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    size_bytes: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )

    sha256: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        index=True,
    )

    object_key: Mapped[str | None] = mapped_column(
        String(1024),
        nullable=True,
        unique=True,
    )

    storage_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=DocumentStorageStatus.PENDING.value,
    )

    extraction_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=DocumentExtractionStatus.PENDING.value,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class Operation(Base):
    __tablename__ = "operations"
    __table_args__ = (
        Index(
            "ix_operations_tenant_status",
            "tenant_id",
            "status",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    tenant_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )

    tender_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("tender_versions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    request_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        unique=True,
    )

    thread_id: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        unique=True,
    )

    stage: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="tender_understanding",
    )

    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=OperationStatus.QUEUED.value,
    )

    attempt: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    result_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    error_code: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )

    error_detail: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

class DocumentExtraction(Base):
    __tablename__ = "document_extractions"
    __table_args__ = (
        UniqueConstraint(
            "document_id",
            name="uq_document_extractions_document",
        ),
        Index(
            "ix_document_extractions_status",
            "status",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    document_id: Mapped[UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )

    extracted_text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
    )

    character_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    page_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    warnings_json: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )

    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class DocumentPage(Base):
    __tablename__ = "document_pages"
    __table_args__ = (
        UniqueConstraint(
            "extraction_id",
            "page_number",
            name="uq_document_pages_extraction_number",
        ),
        Index(
            "ix_document_pages_extraction_ocr",
            "extraction_id",
            "ocr_required",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    extraction_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "document_extractions.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    page_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    source_page_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default=text("1"),
    )

    source_name: Mapped[str] = mapped_column(
        String(1024),
        nullable=False,
    )

    native_text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
        server_default="",
    )

    extracted_text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
    )

    character_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    extraction_method: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    ocr_required: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )

    quality_score: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    quality_metrics_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )

    ocr_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="not_required",
        server_default="not_required",
    )

    ocr_text: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    ocr_provider: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    ocr_confidence: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    ocr_attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )

    ocr_error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    warnings_json: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )

    layout_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class DocumentClassification(Base):
    __tablename__ = "document_classifications"
    __table_args__ = (
        UniqueConstraint(
            "document_id",
            name="uq_document_classifications_document",
        ),
        Index(
            "ix_document_classifications_type_review",
            "primary_document_type",
            "needs_review",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    document_id: Mapped[UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    primary_document_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    content_role: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="tender_source",
    )

    confidence: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
    )

    needs_review: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )

    type_breakdown_json: Mapped[dict[str, int]] = (
        mapped_column(
            JSONB,
            nullable=False,
            default=dict,
            server_default=text("'{}'::jsonb"),
        )
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class PageClassification(Base):
    __tablename__ = "page_classifications"
    __table_args__ = (
        UniqueConstraint(
            "page_id",
            name="uq_page_classifications_page",
        ),
        Index(
            "ix_page_classifications_type",
            "document_type",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    document_classification_id: Mapped[UUID] = (
        mapped_column(
            ForeignKey(
                "document_classifications.id",
                ondelete="CASCADE",
            ),
            nullable=False,
            index=True,
        )
    )

    page_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "document_pages.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    document_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    content_role: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    title: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    confidence: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    reason: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    signals_json: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )

    classification_method: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

class LogicalDocument(Base):
    __tablename__ = "logical_documents"
    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "sequence_number",
            name="uq_logical_documents_document_sequence",
        ),
        Index(
            "ix_logical_documents_type_review",
            "document_type",
            "needs_review",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    document_id: Mapped[UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    sequence_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    document_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    content_role: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    title: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    source_name: Mapped[str] = mapped_column(
        String(1024),
        nullable=False,
    )

    start_page_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    end_page_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    start_source_page_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    end_source_page_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    page_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    confidence: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    needs_review: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )

    boundary_reason: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class LogicalDocumentPage(Base):
    __tablename__ = "logical_document_pages"
    __table_args__ = (
        UniqueConstraint(
            "logical_document_id",
            "sequence_number",
            name=(
                "uq_logical_document_pages_"
                "logical_sequence"
            ),
        ),
        UniqueConstraint(
            "page_id",
            name="uq_logical_document_pages_page",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    logical_document_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "logical_documents.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    page_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "document_pages.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    sequence_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

class TenderSourcePlan(Base):
    __tablename__ = "tender_source_plans"
    __table_args__ = (
        UniqueConstraint(
            "tender_version_id",
            name="uq_tender_source_plans_version",
        ),
        Index(
            "ix_tender_source_plans_status_review",
            "status",
            "needs_review",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    tender_version_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "tender_versions.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    primary_base_logical_document_id: Mapped[UUID] = (
        mapped_column(
            ForeignKey(
                "logical_documents.id",
                ondelete="CASCADE",
            ),
            nullable=False,
            index=True,
        )
    )

    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="base_selected",
    )

    confidence: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    needs_review: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )

    selection_reason: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    warnings_json: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class TenderSourcePlanMember(Base):
    __tablename__ = "tender_source_plan_members"
    __table_args__ = (
        UniqueConstraint(
            "source_plan_id",
            "logical_document_id",
            name=(
                "uq_tender_source_plan_members_"
                "plan_document"
            ),
        ),
        UniqueConstraint(
            "source_plan_id",
            "precedence_order",
            name=(
                "uq_tender_source_plan_members_"
                "plan_order"
            ),
        ),
        Index(
            "ix_tender_source_plan_members_role_binding",
            "source_role",
            "binding_status",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    source_plan_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "tender_source_plans.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    logical_document_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "logical_documents.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    source_role: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    precedence_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    binding_status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    issued_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    reference_number: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    confidence: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    reason: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

class RetrievalIndex(Base):
    __tablename__ = "retrieval_indexes"
    __table_args__ = (
        UniqueConstraint(
            "tender_version_id",
            name=(
                "uq_retrieval_indexes_"
                "tender_version"
            ),
        ),
        UniqueConstraint(
            "source_plan_id",
            name=(
                "uq_retrieval_indexes_"
                "source_plan"
            ),
        ),
        Index(
            "ix_retrieval_indexes_status",
            "status",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    tender_version_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "tender_versions.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    source_plan_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "tender_source_plans.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="building",
    )

    embedding_provider: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    embedding_model: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    embedding_dimensions: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    reranker_provider: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    reranker_model: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    chunk_characters: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    chunk_overlap_characters: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    chunk_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )

    indexed_page_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )

    skipped_page_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class RetrievalChunk(Base):
    __tablename__ = "retrieval_chunks"
    __table_args__ = (
        UniqueConstraint(
            "retrieval_index_id",
            "logical_document_id",
            "sequence_number",
            name=(
                "uq_retrieval_chunks_"
                "index_document_sequence"
            ),
        ),
        Index(
            "ix_retrieval_chunks_authority",
            "source_role",
            "binding_status",
            "precedence_order",
        ),
        Index(
            "ix_retrieval_chunks_page",
            "page_id",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    retrieval_index_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "retrieval_indexes.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    logical_document_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "logical_documents.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    document_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "documents.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    page_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "document_pages.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    sequence_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    source_role: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    binding_status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    precedence_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    logical_document_title: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    heading: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    source_name: Mapped[str] = mapped_column(
        String(1024),
        nullable=False,
    )

    page_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    source_page_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    text_content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    token_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    chunk_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )

    embedding_json: Mapped[list[float]] = mapped_column(
        JSONB,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
class TenderFieldUnderstandingRun(Base):
    __tablename__ = "tender_field_understanding_runs"
    __table_args__ = (
        UniqueConstraint(
            "tender_version_id",
            name=(
                "uq_tender_field_understanding_runs_version"
            ),
        ),
        Index(
            "ix_field_understanding_runs_status",
            "status",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    tender_version_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "tender_versions.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    retrieval_index_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "retrieval_indexes.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    catalog_schema_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    catalog_schema_version: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="completed",
    )

    llm_provider: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    llm_model: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    configured_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    found_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    not_found_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    ambiguous_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    error_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    warnings_json: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class TenderFieldResult(Base):
    __tablename__ = "tender_field_results"
    __table_args__ = (
        UniqueConstraint(
            "understanding_run_id",
            "field_key",
            name="uq_tender_field_results_run_key",
        ),
        Index(
            "ix_tender_field_results_status_review",
            "status",
            "needs_review",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    understanding_run_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "tender_field_understanding_runs.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    field_key: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    section_key: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    label: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    value_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    raw_value_json: Mapped[Any | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    display_value: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    confidence: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    explanation: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    search_query: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    needs_review: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class TenderFieldEvidence(Base):
    __tablename__ = "tender_field_evidence"
    __table_args__ = (
        UniqueConstraint(
            "field_result_id",
            "retrieval_chunk_id",
            "quote",
            name="uq_tender_field_evidence_result_chunk_quote",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    field_result_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "tender_field_results.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    retrieval_chunk_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "retrieval_chunks.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    logical_document_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "logical_documents.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    page_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "document_pages.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    source_name: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    page_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    source_role: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    binding_status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    precedence_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    quote: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    retrieval_score: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

class TenderNormalizationRun(Base):
    __tablename__ = "tender_normalization_runs"
    __table_args__ = (
        UniqueConstraint(
            "understanding_run_id",
            name=(
                "uq_tender_normalization_runs_"
                "understanding"
            ),
        ),
        Index(
            "ix_tender_normalization_runs_status",
            "status",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    tender_version_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "tender_versions.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    understanding_run_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "tender_field_understanding_runs.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="normalized",
    )

    default_currency: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
    )

    default_timezone: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    normalized_field_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    unavailable_field_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    candidate_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    normalization_error_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    reconciled_field_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    conflict_field_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    unresolved_field_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    warnings_json: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class TenderNormalizedField(Base):
    __tablename__ = "tender_normalized_fields"
    __table_args__ = (
        UniqueConstraint(
            "normalization_run_id",
            "field_key",
            name=(
                "uq_tender_normalized_fields_run_key"
            ),
        ),
        Index(
            "ix_tender_normalized_fields_status_review",
            "status",
            "needs_review",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    normalization_run_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "tender_normalization_runs.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    source_field_result_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "tender_field_results.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    field_key: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    section_key: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    label: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    value_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    source_status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    source_confidence: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    source_needs_review: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )

    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    effective_value_json: Mapped[Any | None] = (
        mapped_column(
            JSONB,
            nullable=True,
        )
    )

    effective_display_value: Mapped[str | None] = (
        mapped_column(
            Text,
            nullable=True,
        )
    )

    needs_review: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )

    conflict_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    warnings_json: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class TenderNormalizedCandidate(Base):
    __tablename__ = "tender_normalized_candidates"
    __table_args__ = (
        UniqueConstraint(
            "normalized_field_id",
            "ordinal",
            name=(
                "uq_tender_normalized_candidates_"
                "field_ordinal"
            ),
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    normalized_field_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "tender_normalized_fields.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    ordinal: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    label: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    raw_value_json: Mapped[Any] = mapped_column(
        JSONB,
        nullable=False,
    )

    normalized_kind: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    normalized_value_json: Mapped[Any] = mapped_column(
        JSONB,
        nullable=False,
    )

    normalized_key: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    confidence: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    binding_status: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    source_role: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    precedence_order: Mapped[int | None] = (
        mapped_column(
            Integer,
            nullable=True,
        )
    )

    retrieval_score: Mapped[float | None] = (
        mapped_column(
            Float,
            nullable=True,
        )
    )

    evidence_match_degraded: Mapped[bool] = (
        mapped_column(
            Boolean,
            nullable=False,
            default=False,
            server_default=text("false"),
        )
    )

    selected: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )

    resolution_status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="pending",
    )

    resolution_reason: Mapped[str | None] = (
        mapped_column(
            Text,
            nullable=True,
        )
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class TenderNormalizedCandidateEvidence(Base):
    __tablename__ = (
        "tender_normalized_candidate_evidence"
    )
    __table_args__ = (
        UniqueConstraint(
            "normalized_candidate_id",
            "field_evidence_id",
            name=(
                "uq_normalized_candidate_evidence_pair"
            ),
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    normalized_candidate_id: Mapped[UUID] = (
        mapped_column(
            ForeignKey(
                "tender_normalized_candidates.id",
                ondelete="CASCADE",
            ),
            nullable=False,
            index=True,
        )
    )

    field_evidence_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "tender_field_evidence.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

class TenderRequirementRun(Base):
    __tablename__ = "tender_requirement_runs"
    __table_args__ = (
        UniqueConstraint(
            "normalization_run_id",
            name=(
                "uq_tender_requirement_runs_"
                "normalization"
            ),
        ),
        Index(
            "ix_tender_requirement_runs_status",
            "status",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    tender_version_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "tender_versions.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    normalization_run_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "tender_normalization_runs.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    retrieval_index_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "retrieval_indexes.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    catalog_schema_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    catalog_schema_version: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="requirements_extracted",
    )

    llm_provider: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    llm_model: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    requirement_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    mandatory_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    conditional_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    informational_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    validated_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    review_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    invalid_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    warnings_json: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class TenderRequirement(Base):
    __tablename__ = "tender_requirements"
    __table_args__ = (
        UniqueConstraint(
            "requirement_run_id",
            "requirement_code",
            name=(
                "uq_tender_requirements_run_code"
            ),
        ),
        Index(
            "ix_tender_requirements_category_status",
            "category_key",
            "validation_status",
        ),
        Index(
            "ix_tender_requirements_review",
            "needs_review",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    requirement_run_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "tender_requirement_runs.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    requirement_code: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    category_key: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    category_label: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    requirement_text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    obligation_level: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    condition_text: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    bidder_proof_json: Mapped[list[str]] = (
        mapped_column(
            JSONB,
            nullable=False,
            default=list,
            server_default=text("'[]'::jsonb"),
        )
    )

    confidence: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    validation_status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="pending_validation",
    )

    needs_review: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )

    warnings_json: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class TenderRequirementEvidence(Base):
    __tablename__ = "tender_requirement_evidence"
    __table_args__ = (
        UniqueConstraint(
            "requirement_id",
            "retrieval_chunk_id",
            "quote",
            name=(
                "uq_tender_requirement_evidence_"
                "requirement_chunk_quote"
            ),
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    requirement_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "tender_requirements.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    retrieval_chunk_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "retrieval_chunks.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    logical_document_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "logical_documents.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    page_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "document_pages.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    source_name: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    page_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    source_role: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    binding_status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    precedence_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    quote: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    retrieval_score: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    is_valid: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
    )

    validation_message: Mapped[str | None] = (
        mapped_column(
            Text,
            nullable=True,
        )
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

class TenderFinalizationRun(Base):
    __tablename__ = "tender_finalization_runs"
    __table_args__ = (
        UniqueConstraint(
            "requirement_run_id",
            name=(
                "uq_tender_finalization_runs_"
                "requirement"
            ),
        ),
        Index(
            "ix_tender_finalization_status",
            "status",
        ),
        Index(
            "ix_tender_finalization_review",
            "ready_for_review",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    tender_version_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "tender_versions.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    normalization_run_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "tender_normalization_runs.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    requirement_run_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "tender_requirement_runs.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    policy_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    policy_version: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    ready_for_review: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )

    readiness_score: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    field_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    requirement_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    issue_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    warning_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    error_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    fatal_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    profile_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
    )

    coverage_metrics_json: Mapped[
        dict[str, Any]
    ] = mapped_column(
        JSONB,
        nullable=False,
    )

    review_reasons_json: Mapped[list[str]] = (
        mapped_column(
            JSONB,
            nullable=False,
            default=list,
            server_default=text("'[]'::jsonb"),
        )
    )

    summary: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class TenderFinalizationIssue(Base):
    __tablename__ = "tender_finalization_issues"
    __table_args__ = (
        Index(
            "ix_tender_finalization_issues_severity",
            "severity",
        ),
        Index(
            "ix_tender_finalization_issues_review",
            "requires_review",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    finalization_run_id: Mapped[UUID] = (
        mapped_column(
            ForeignKey(
                "tender_finalization_runs.id",
                ondelete="CASCADE",
            ),
            nullable=False,
            index=True,
        )
    )

    code: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    severity: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    category: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    entity_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    entity_key: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    message: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    requires_review: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )

    fatal: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class TenderReviewSession(Base):
    __tablename__ = "tender_review_sessions"
    __table_args__ = (
        UniqueConstraint(
            "finalization_run_id",
            name="uq_tender_review_sessions_finalization",
        ),
        UniqueConstraint(
            "thread_id",
            name="uq_tender_review_sessions_thread",
        ),
        Index(
            "ix_tender_review_sessions_tenant_status",
            "tenant_id",
            "status",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid4
    )
    tenant_id: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True
    )
    finalization_run_id: Mapped[UUID] = mapped_column(
        ForeignKey("tender_finalization_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tender_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("tender_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    thread_id: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    package_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    original_profile_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False
    )
    corrected_profile_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True
    )
    decision: Mapped[str | None] = mapped_column(String(50), nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewer_user_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )
    correction_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class TenderReviewCorrection(Base):
    __tablename__ = "tender_review_corrections"
    __table_args__ = (
        UniqueConstraint(
            "review_session_id",
            "ordinal",
            name="uq_tender_review_corrections_ordinal",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid4
    )
    review_session_id: Mapped[UUID] = mapped_column(
        ForeignKey("tender_review_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    target_type: Mapped[str] = mapped_column(String(50), nullable=False)
    target_key: Mapped[str] = mapped_column(String(255), nullable=False)
    patch_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    applied: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        Index(
            "ix_audit_events_entity",
            "entity_type",
            "entity_id",
        ),
        Index(
            "ix_audit_events_tenant_created",
            "tenant_id",
            "created_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    tenant_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )

    actor_user_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    event_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    entity_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    entity_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    before_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    after_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
