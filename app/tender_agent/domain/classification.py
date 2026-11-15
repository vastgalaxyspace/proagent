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
    "bid_covering_letter",
    "technical_proposal",
    "financial_bid",
    "bid_submission",
    "emd_or_bid_security",
    "bid_security_declaration",
    "bank_guarantee",
    "mse_udyam_or_startup_exemption",
    "mii_local_content",
    "land_border_declaration",
    "oem_authorization",
    "poa_or_board_authorization",
    "gst_pan_cin_statutory",
    "gem_registration",
    "registration_document",
    "statutory_license",
    "environmental_statutory",
    "labour_compliance",
    "turnover_networth_ca_certificate",
    "audited_financials_or_itr",
    "bank_solvency",
    "experience_po_completion",
    "past_work_evidence",
    "quality_certificate",
    "calibration_certificate",
    "datasheet_catalogue",
    "integrity_pact",
    "integrity_blacklisting_declaration",
    "non_blacklisting_declaration",
    "nil_deviation_declaration",
    "tender_acceptance",
    "techno_commercial_compliance",
    "consortium_jv",
    "commercial_or_price",
    "other",
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
class SourceClassificationDecision:
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
