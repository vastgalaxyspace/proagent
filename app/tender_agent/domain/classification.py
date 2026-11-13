from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from uuid import UUID


TenderDocumentType = Literal[
    "tender_notice",
    "rfp_or_bid_document",
    "gem_bid",
    "corrigendum",
    "prebid_clarification",
    "atc_stc_sla_gtc",
    "technical_specs_or_sow",
    "eligibility_pqc",
    "boq_or_price_schedule",
    "forms_annexures",
    "contract_terms",
    "unknown",
]


ContentRole = Literal[
    "tender_source",
    "reference",
    "unknown",
]


@dataclass(frozen=True)
class PageClassificationDecision:
    page_id: UUID
    document_type: TenderDocumentType
    content_role: ContentRole
    title: str
    confidence: float
    reason: str
    signals: list[str]
    classification_method: str


@dataclass(frozen=True)
class DocumentClassificationDecision:
    document_id: UUID
    primary_document_type: TenderDocumentType
    content_role: ContentRole
    confidence: float
    needs_review: bool
    type_breakdown: dict[str, int]