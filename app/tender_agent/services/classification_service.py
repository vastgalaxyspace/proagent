from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from uuid import UUID

from app.tender_agent.domain.classification import (
    DocumentClassificationDecision,
    PageClassificationDecision,
    SourceClassificationDecision,
    TenderDocumentType,
)


@dataclass(frozen=True)
class ClassificationLimits:
    probe_characters: int = 4000
    minimum_confidence: float = 0.60


class TenderClassificationService:
    """Historical deterministic tender classifier for LangGraph."""

    _TENDER_SOURCE_MARKERS = (
        "tender document",
        "notice inviting tender",
        "request for proposal",
        "bid document",
        "e-tender",
    )

    _DOCUMENT_RULES: tuple[
        tuple[TenderDocumentType, tuple[str, ...]], ...
    ] = (
        ("gem_bid", ("gem-bidding", "bid details", "bid number")),
        (
            "atc_stc_sla_gtc",
            (
                "buyer added",
                "additional terms",
                "general purchase condition",
                "gpc",
            ),
        ),
        (
            "mse_udyam_or_startup_exemption",
            (
                "udyam",
                "msme registration",
                "mse certificate",
                "enterprise type micro",
            ),
        ),
        (
            "land_border_declaration",
            (
                "country sharing land border",
                "land border with india",
                "rule 144 xi",
                "competent authority registration",
            ),
        ),
        (
            "integrity_pact",
            ("integrity pact", "independent external monitor"),
        ),
        (
            "non_blacklisting_declaration",
            ("holiday", "banning", "blacklisted", "debar"),
        ),
        (
            "nil_deviation_declaration",
            ("nil deviation", "no deviation"),
        ),
        (
            "techno_commercial_compliance",
            (
                "techno-commercial bid",
                "techno commercial bid",
                "techno-commercial compliance",
                "techno commercial compliance",
                "unpriced commercial compliance",
            ),
        ),
        (
            "mii_local_content",
            (
                "local content",
                "public procurement",
                "make in india",
                "pplc",
            ),
        ),
        (
            "technical_proposal",
            (
                "technical specification",
                "technicalspec",
                "technical spec",
            ),
        ),
        (
            "datasheet_catalogue",
            (
                "technical data sheet",
                "property specification",
                "nominal thickness",
                "product catalogue",
            ),
        ),
        (
            "quality_certificate",
            (
                "iso ",
                "iso-",
                "quality management certificate",
                "quality certificate",
                "test certificate",
            ),
        ),
        ("corrigendum", ("corrigendum",)),
        (
            "boq_or_price_schedule",
            ("boq", "price schedule", "commercial details", "quoted"),
        ),
    )

    def __init__(self, limits: ClassificationLimits) -> None:
        self.limits = limits

    def classify_source(
        self,
        *,
        source_name: str,
        text: str,
    ) -> SourceClassificationDecision:
        if not text.strip():
            return SourceClassificationDecision(
                document_type="unknown",
                content_role="tender_source",
                title=source_name,
                confidence=0.0,
                reason="No extractable text.",
                signals=[],
                classification_method="old_empty_source",
            )

        name = source_name.lower()
        probe = text[:2000].lower()
        haystack = f"{name}\n{probe}"
        tender_signals = [
            marker
            for marker in self._TENDER_SOURCE_MARKERS
            if marker in haystack
        ]

        if tender_signals:
            return SourceClassificationDecision(
                document_type="rfp_or_bid_document",
                content_role="tender_source",
                title=source_name,
                confidence=0.8,
                reason="Matched tender-source document markers locally.",
                signals=tender_signals,
                classification_method="old_document_heuristic",
            )

        for document_type, markers in self._DOCUMENT_RULES:
            matched = [
                marker for marker in markers if marker in haystack
            ]

            if matched:
                return SourceClassificationDecision(
                    document_type=document_type,
                    content_role="tender_source",
                    title=source_name,
                    confidence=0.75,
                    reason=(
                        "Matched filename/text procurement keywords "
                        "locally."
                    ),
                    signals=matched,
                    classification_method="old_document_heuristic",
                )

        return SourceClassificationDecision(
            document_type="rfp_or_bid_document",
            content_role="tender_source",
            title=source_name,
            confidence=0.35,
            reason=(
                "Generic local fallback; no model classification was "
                "requested."
            ),
            signals=[],
            classification_method="old_document_fallback",
        )

    def classify_page(
        self,
        *,
        page_id: UUID,
        page_number: int,
        source_name: str,
        text: str,
        inherited: SourceClassificationDecision,
    ) -> PageClassificationDecision:
        boundary = self._strong_page_boundary(
            page_id=page_id,
            page_number=page_number,
            source_name=source_name,
            text=text,
        )

        if boundary is not None:
            return boundary

        return PageClassificationDecision(
            page_id=page_id,
            document_type=inherited.document_type,
            content_role=inherited.content_role,
            title=inherited.title,
            confidence=inherited.confidence,
            reason=inherited.reason,
            signals=list(inherited.signals),
            classification_method="old_document_inheritance",
        )

    @staticmethod
    def source_from_boundary(
        decision: PageClassificationDecision,
    ) -> SourceClassificationDecision:
        return SourceClassificationDecision(
            document_type=decision.document_type,
            content_role=decision.content_role,
            title=decision.title,
            confidence=decision.confidence,
            reason=decision.reason,
            signals=list(decision.signals),
            classification_method=decision.classification_method,
        )

    def summarize_document(
        self,
        *,
        document_id: UUID,
        decisions: list[PageClassificationDecision],
    ) -> DocumentClassificationDecision:
        if not decisions:
            return DocumentClassificationDecision(
                document_id=document_id,
                primary_document_type="unknown",
                content_role="unknown",
                confidence=0.0,
                needs_review=True,
                type_breakdown={},
            )

        type_counts = Counter(
            decision.document_type for decision in decisions
        )
        primary_type = type_counts.most_common(1)[0][0]
        primary_decision = max(
            (
                decision
                for decision in decisions
                if decision.document_type == primary_type
            ),
            key=lambda decision: decision.confidence,
        )
        average_confidence = sum(
            decision.confidence for decision in decisions
        ) / len(decisions)
        needs_review = any(
            decision.document_type == "unknown"
            or decision.confidence < self.limits.minimum_confidence
            for decision in decisions
        )

        return DocumentClassificationDecision(
            document_id=document_id,
            primary_document_type=primary_decision.document_type,
            content_role=primary_decision.content_role,
            confidence=round(average_confidence, 4),
            needs_review=needs_review,
            type_breakdown=dict(type_counts),
        )

    def _strong_page_boundary(
        self,
        *,
        page_id: UUID,
        page_number: int,
        source_name: str,
        text: str,
    ) -> PageClassificationDecision | None:
        heading_lines = [
            self._normalize_for_match(line)
            for line in text.splitlines()[:24]
            if self._normalize_for_match(line)
        ]

        if not heading_lines:
            return None

        corrigendum_heading = next(
            (
                line
                for line in heading_lines[:12]
                if re.match(
                    r"^(?:(?:corrigendum(?:\s*(?:/|cum)\s*addendum)?|addendum)"
                    r"(?:\s+(?:(?:no\.?|number|#)?\s*[-:#]?\s*\d+\b.*|"
                    r"(?:dated|to|for)\b.*))?|(?:amendment\s+to\s+"
                    r"(?:rfp|tender)|tender\s+amendment)\b.*)$",
                    line,
                )
            ),
            "",
        )

        if corrigendum_heading:
            title = re.sub(
                r"\s+page\s+\d+\s+of\s+\d+\s*$",
                "",
                corrigendum_heading,
            ).strip()
            return self._boundary_decision(
                page_id=page_id,
                document_type="corrigendum",
                title=title,
                reason=(
                    "Strong page boundary: corrigendum/addendum heading."
                ),
            )

        prebid_heading = next(
            (
                line
                for line in heading_lines[:12]
                if re.match(
                    r"^(?:pre[- ]?bid clarification|pre[- ]?bid queries|"
                    r"pre[- ]?bid query reply|reply to pre[- ]?bid queries|"
                    r"response to pre[- ]?bid queries)\b",
                    line,
                )
            ),
            "",
        )

        if prebid_heading:
            return self._boundary_decision(
                page_id=page_id,
                document_type="prebid_clarification",
                title=prebid_heading,
                reason=(
                    "Strong page boundary: pre-bid clarification heading."
                ),
            )

        rfp_heading = next(
            (
                line
                for line in heading_lines[:12]
                if re.match(
                    r"^(?:request for proposal|rfp for\b|"
                    r"notice inviting tender|invitation for bids|"
                    r"tender document(?:\s+for\b|$))",
                    line,
                )
            ),
            "",
        )

        if rfp_heading:
            return self._boundary_decision(
                page_id=page_id,
                document_type="rfp_or_bid_document",
                title=f"{source_name} page {page_number}",
                reason=(
                    "Strong page boundary: base RFP/tender heading."
                ),
            )

        return None

    @staticmethod
    def _boundary_decision(
        *,
        page_id: UUID,
        document_type: TenderDocumentType,
        title: str,
        reason: str,
    ) -> PageClassificationDecision:
        confidence = (
            0.9
            if document_type == "rfp_or_bid_document"
            else 0.95
        )
        return PageClassificationDecision(
            page_id=page_id,
            document_type=document_type,
            content_role="tender_source",
            title=title[:500],
            confidence=confidence,
            reason=reason,
            signals=[title],
            classification_method="deterministic_heading",
        )

    @staticmethod
    def _normalize_for_match(value: str) -> str:
        return re.sub(r"\s+", " ", value).strip().lower()
