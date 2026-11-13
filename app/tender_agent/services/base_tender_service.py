from __future__ import annotations

from app.tender_agent.domain.authority import (
    BaseTenderSelection,
    TenderSourceCandidate,
)


class BaseTenderService:
    BASE_TYPE_SCORES = {
        "rfp_or_bid_document": 100.0,
        "gem_bid": 95.0,
        "tender_notice": 80.0,
        "technical_specs_or_sow": 55.0,
        "atc_stc_sla_gtc": 50.0,
        "contract_terms": 45.0,
    }

    POST_BASE_TYPES = {
        "corrigendum",
        "prebid_clarification",
    }

    def select_base_tender(
        self,
        candidates: list[TenderSourceCandidate],
    ) -> BaseTenderSelection:
        if not candidates:
            raise ValueError(
                "No logical documents were available for "
                "base-tender selection."
            )

        eligible_candidates = [
            candidate
            for candidate in candidates
            if candidate.document_type
            in self.BASE_TYPE_SCORES
        ]

        fallback_used = False

        if not eligible_candidates:
            eligible_candidates = [
                candidate
                for candidate in candidates
                if candidate.document_type
                not in self.POST_BASE_TYPES
            ]
            fallback_used = True

        if not eligible_candidates:
            raise ValueError(
                "No base-tender candidate was found."
            )

        ranked = sorted(
            (
                (
                    self._score(candidate),
                    candidate,
                )
                for candidate in eligible_candidates
            ),
            key=lambda item: (
                -item[0],
                item[1].sequence_number,
                str(item[1].logical_document_id),
            ),
        )

        best_score, primary = ranked[0]

        ambiguous = bool(
            len(ranked) > 1
            and best_score - ranked[1][0] < 3.0
        )

        supporting_ids = [
            candidate.logical_document_id
            for candidate in candidates
            if (
                candidate.logical_document_id
                != primary.logical_document_id
                and candidate.document_type
                not in self.POST_BASE_TYPES
            )
        ]

        needs_review = bool(
            fallback_used
            or ambiguous
            or primary.needs_review
            or primary.document_type
            not in {
                "rfp_or_bid_document",
                "gem_bid",
                "tender_notice",
            }
        )

        reasons: list[str] = [
            "Selected the highest-ranked authoritative "
            "tender source."
        ]

        if fallback_used:
            reasons.append(
                "No standard base-tender type was found; "
                "fallback selection was used."
            )

        if ambiguous:
            reasons.append(
                "The top two base candidates had similar "
                "scores."
            )

        return BaseTenderSelection(
            primary_logical_document_id=(
                primary.logical_document_id
            ),
            supporting_logical_document_ids=(
                supporting_ids
            ),
            confidence=round(
                min(1.0, best_score / 110.0),
                4,
            ),
            needs_review=needs_review,
            reason=" ".join(reasons),
        )

    def _score(
        self,
        candidate: TenderSourceCandidate,
    ) -> float:
        type_score = self.BASE_TYPE_SCORES.get(
            candidate.document_type,
            25.0,
        )

        confidence_score = candidate.confidence * 10.0
        page_score = min(candidate.page_count, 20) * 0.10

        review_penalty = (
            5.0
            if candidate.needs_review
            else 0.0
        )

        return (
            type_score
            + confidence_score
            + page_score
            - review_penalty
        )