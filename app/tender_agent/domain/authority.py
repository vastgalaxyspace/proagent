from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal
from uuid import UUID


SourceRole = Literal[
    "primary_base",
    "base_supporting",
    "corrigendum",
    "prebid_clarification",
    "reference",
]


BindingStatus = Literal[
    "binding",
    "non_binding",
    "review_required",
]


AmendmentOperation = Literal[
    "replace",
    "add",
    "delete",
    "clarify",
]


@dataclass(frozen=True)
class AmendmentSourcePage:
    page_id: UUID
    page_number: int
    source_page_number: int
    text: str


@dataclass(frozen=True)
class AmendmentOperationDraft:
    logical_document_id: UUID
    page_id: UUID
    operation: AmendmentOperation
    target: str
    previous_value: Any | None
    revised_value: Any | None
    evidence_quote: str
    confidence: float
    validation_status: Literal[
        "validated",
        "review_required",
    ]
    reason: str


@dataclass(frozen=True)
class TenderSourceCandidate:
    logical_document_id: UUID
    document_id: UUID

    sequence_number: int
    document_type: str
    content_role: str
    title: str
    source_name: str

    page_count: int
    confidence: float
    needs_review: bool
    text: str
    pages: list[AmendmentSourcePage]


@dataclass(frozen=True)
class BaseTenderSelection:
    primary_logical_document_id: UUID
    supporting_logical_document_ids: list[UUID]
    authoritative_logical_document_ids: list[UUID]
    excluded_reference_logical_document_ids: list[UUID]

    confidence: float
    needs_review: bool
    reason: str


@dataclass(frozen=True)
class SourcePlanMemberDraft:
    logical_document_id: UUID

    source_role: SourceRole
    precedence_order: int
    binding_status: BindingStatus

    issued_at: datetime | None
    reference_number: str | None

    confidence: float
    reason: str


@dataclass(frozen=True)
class EffectiveTenderPlanDraft:
    members: list[SourcePlanMemberDraft]
    operations: list[AmendmentOperationDraft]
    needs_review: bool
    warnings: list[str]
