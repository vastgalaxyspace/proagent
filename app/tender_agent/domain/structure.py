from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.tender_agent.domain.classification import (
    ContentRole,
    TenderDocumentType,
)


@dataclass(frozen=True)
class ClassifiedPage:
    page_id: UUID
    document_id: UUID

    page_number: int
    source_page_number: int
    source_name: str

    document_type: TenderDocumentType
    content_role: ContentRole
    title: str
    confidence: float
    reason: str
    classification_method: str


@dataclass(frozen=True)
class LogicalDocumentDraft:
    document_id: UUID
    sequence_number: int

    document_type: TenderDocumentType
    content_role: ContentRole
    title: str

    source_name: str
    start_page_number: int
    end_page_number: int
    start_source_page_number: int
    end_source_page_number: int
    page_count: int

    confidence: float
    needs_review: bool
    boundary_reason: str

    page_ids: list[UUID]