from __future__ import annotations

import re
from uuid import UUID

from app.tender_agent.domain.retrieval import (
    StoredRetrievalChunk,
)
from app.tender_agent.domain.values import (
    EvidenceValidationBuildResult,
    EvidenceValidationDecision,
    RequirementValidationDecision,
    StoredRequirement,
)


class EvidenceService:
    def validate(
        self,
        *,
        requirements: list[StoredRequirement],
        chunks: list[StoredRetrievalChunk],
    ) -> EvidenceValidationBuildResult:
        chunks_by_id = {
            chunk.chunk_id: chunk
            for chunk in chunks
        }

        decisions = [
            self._validate_requirement(
                requirement=requirement,
                chunks_by_id=chunks_by_id,
            )
            for requirement in requirements
        ]

        review_codes = [
            decision.requirement_code
            for decision in decisions
            if decision.validation_status == "needs_review"
        ]

        invalid_codes = [
            decision.requirement_code
            for decision in decisions
            if decision.validation_status == "invalid"
        ]

        return EvidenceValidationBuildResult(
            requirements=decisions,
            validated_count=sum(
                decision.validation_status
                == "validated"
                for decision in decisions
            ),
            review_count=sum(
                decision.validation_status
                == "needs_review"
                for decision in decisions
            ),
            invalid_count=len(invalid_codes),
            review_requirement_codes=review_codes,
            invalid_requirement_codes=invalid_codes,
            warnings=[
                (
                    f"{decision.requirement_code}: "
                    + "; ".join(decision.warnings)
                )
                for decision in decisions
                if decision.warnings
            ],
        )

    def _validate_requirement(
        self,
        *,
        requirement: StoredRequirement,
        chunks_by_id: dict[
            UUID,
            StoredRetrievalChunk,
        ],
    ) -> RequirementValidationDecision:
        evidence_decisions: list[
            EvidenceValidationDecision
        ] = []
        warnings: list[str] = []

        valid_binding_count = 0
        valid_review_count = 0

        for evidence in requirement.evidence:
            chunk = chunks_by_id.get(
                evidence.chunk_id
            )

            if chunk is None:
                evidence_decisions.append(
                    EvidenceValidationDecision(
                        evidence_id=evidence.evidence_id,
                        is_valid=False,
                        validation_message=(
                            "Retrieval chunk does not exist."
                        ),
                    )
                )
                continue

            if (
                chunk.logical_document_id
                != evidence.logical_document_id
                or chunk.page_id != evidence.page_id
                or chunk.source_role
                != evidence.source_role
                or chunk.binding_status
                != evidence.binding_status
                or chunk.precedence_order
                != evidence.precedence_order
            ):
                evidence_decisions.append(
                    EvidenceValidationDecision(
                        evidence_id=evidence.evidence_id,
                        is_valid=False,
                        validation_message=(
                            "Evidence source metadata does "
                            "not match the retrieval chunk."
                        ),
                    )
                )
                continue

            if not self._quote_is_supported(
                quote=evidence.quote,
                text=chunk.text,
            ):
                evidence_decisions.append(
                    EvidenceValidationDecision(
                        evidence_id=evidence.evidence_id,
                        is_valid=False,
                        validation_message=(
                            "Evidence quote is not present "
                            "in the source chunk."
                        ),
                    )
                )
                continue

            if chunk.binding_status == "binding":
                valid_binding_count += 1
                message = (
                    "Evidence is grounded in a binding "
                    "tender source."
                )
            elif (
                chunk.binding_status
                == "review_required"
            ):
                valid_review_count += 1
                message = (
                    "Evidence is grounded, but source "
                    "authority requires human review."
                )
            else:
                evidence_decisions.append(
                    EvidenceValidationDecision(
                        evidence_id=evidence.evidence_id,
                        is_valid=False,
                        validation_message=(
                            "Evidence comes from a "
                            "non-binding source."
                        ),
                    )
                )
                continue

            evidence_decisions.append(
                EvidenceValidationDecision(
                    evidence_id=evidence.evidence_id,
                    is_valid=True,
                    validation_message=message,
                )
            )

        if valid_binding_count > 0:
            status = (
                "needs_review"
                if requirement.extraction_needs_review
                else "validated"
            )
        elif valid_review_count > 0:
            status = "needs_review"
            warnings.append(
                "No binding evidence exists; only "
                "review-required evidence is available."
            )
        else:
            status = "invalid"
            warnings.append(
                "The requirement has no valid source "
                "evidence."
            )

        needs_review = (
            status != "validated"
            or requirement.extraction_needs_review
        )

        return RequirementValidationDecision(
            requirement_id=requirement.requirement_id,
            requirement_code=(
                requirement.requirement_code
            ),
            validation_status=status,
            needs_review=needs_review,
            evidence_decisions=evidence_decisions,
            warnings=warnings,
        )

    @staticmethod
    def _quote_is_supported(
        *,
        quote: str,
        text: str,
    ) -> bool:
        normalize = lambda value: re.sub(
            r"\s+",
            " ",
            value.casefold(),
        ).strip()

        normalized_quote = normalize(quote)
        normalized_text = normalize(text)

        return bool(
            normalized_quote
            and normalized_quote in normalized_text
        )
