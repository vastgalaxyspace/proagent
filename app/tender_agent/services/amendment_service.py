from __future__ import annotations

import re
from datetime import datetime, timezone

from app.tender_agent.domain.authority import (
    BaseTenderSelection,
    EffectiveTenderPlanDraft,
    SourcePlanMemberDraft,
    TenderSourceCandidate,
)


class AmendmentService:
    BINDING_PREBID_MARKERS = {
        "shall be read as",
        "is hereby amended",
        "stands amended",
        "tender condition is modified",
        "revised requirement",
        "revised clause",
        "the answer is accepted",
        "buyer response",
        "official response",
    }

    def build_effective_plan(
        self,
        *,
        candidates: list[TenderSourceCandidate],
        selection: BaseTenderSelection,
    ) -> EffectiveTenderPlanDraft:
        if not candidates:
            raise ValueError(
                "No logical documents were available for "
                "amendment resolution."
            )

        by_id = {
            candidate.logical_document_id: candidate
            for candidate in candidates
        }

        primary = by_id.get(
            selection.primary_logical_document_id
        )

        if primary is None:
            raise ValueError(
                "The selected base tender was not found."
            )

        base_candidates = [
            candidate
            for candidate in candidates
            if candidate.document_type
            not in {
                "corrigendum",
                "prebid_clarification",
            }
        ]

        base_candidates.sort(
            key=lambda candidate: (
                candidate.logical_document_id
                != selection.primary_logical_document_id,
                candidate.sequence_number,
                str(candidate.logical_document_id),
            )
        )

        post_base_candidates = [
            candidate
            for candidate in candidates
            if candidate.document_type
            in {
                "corrigendum",
                "prebid_clarification",
            }
        ]

        amendment_metadata = {
            candidate.logical_document_id: (
                self._extract_issued_at(candidate),
                self._extract_reference_number(candidate),
            )
            for candidate in post_base_candidates
        }

        post_base_candidates.sort(
            key=lambda candidate: self._amendment_sort_key(
                candidate,
                amendment_metadata[
                    candidate.logical_document_id
                ][0],
            )
        )

        ordered_candidates = [
            *base_candidates,
            *post_base_candidates,
        ]

        members: list[SourcePlanMemberDraft] = []
        warnings: list[str] = []

        for precedence_order, candidate in enumerate(
            ordered_candidates
        ):
            issued_at, reference_number = (
                amendment_metadata.get(
                    candidate.logical_document_id,
                    (None, None),
                )
            )

            (
                source_role,
                binding_status,
                reason,
            ) = self._authority_for_candidate(
                candidate=candidate,
                selection=selection,
            )

            confidence = candidate.confidence

            if (
                candidate.document_type
                in {
                    "corrigendum",
                    "prebid_clarification",
                }
                and issued_at is None
            ):
                warnings.append(
                    f"{candidate.title}: issue date was not "
                    "found; package order was used."
                )

            if binding_status == "review_required":
                warnings.append(
                    f"{candidate.title}: binding authority "
                    "requires human review."
                )

            members.append(
                SourcePlanMemberDraft(
                    logical_document_id=(
                        candidate.logical_document_id
                    ),
                    source_role=source_role,
                    precedence_order=precedence_order,
                    binding_status=binding_status,
                    issued_at=issued_at,
                    reference_number=reference_number,
                    confidence=confidence,
                    reason=reason,
                )
            )

        needs_review = bool(
            selection.needs_review
            or warnings
            or any(
                member.binding_status
                == "review_required"
                for member in members
            )
        )

        return EffectiveTenderPlanDraft(
            members=members,
            needs_review=needs_review,
            warnings=warnings,
        )

    def _authority_for_candidate(
        self,
        *,
        candidate: TenderSourceCandidate,
        selection: BaseTenderSelection,
    ) -> tuple[str, str, str]:
        if (
            candidate.logical_document_id
            == selection.primary_logical_document_id
        ):
            return (
                "primary_base",
                "binding",
                "Selected as the authoritative base tender.",
            )

        if candidate.document_type == "corrigendum":
            return (
                "corrigendum",
                "binding",
                (
                    "Official corrigendum/addendum is treated "
                    "as a later binding tender source."
                ),
            )

        if (
            candidate.document_type
            == "prebid_clarification"
        ):
            normalized = candidate.text.casefold()

            matched_markers = [
                marker
                for marker in self.BINDING_PREBID_MARKERS
                if marker in normalized
            ]

            if matched_markers:
                return (
                    "prebid_clarification",
                    "binding",
                    (
                        "Pre-bid clarification contains "
                        "official amendment/acceptance language."
                    ),
                )

            return (
                "prebid_clarification",
                "review_required",
                (
                    "Pre-bid clarification was found, but "
                    "binding amendment language was unclear."
                ),
            )

        if candidate.content_role == "reference":
            return (
                "reference",
                "non_binding",
                "Document is classified as reference material.",
            )

        return (
            "base_supporting",
            "binding",
            (
                "Document is part of the original tender "
                "source package."
            ),
        )

    def _extract_issued_at(
        self,
        candidate: TenderSourceCandidate,
    ) -> datetime | None:
        probe = (
            f"{candidate.title}\n"
            f"{candidate.text[:2000]}"
        )

        numeric_patterns = [
            r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b",
            r"\b(\d{4})[/-](\d{1,2})[/-](\d{1,2})\b",
        ]

        first_match = re.search(
            numeric_patterns[0],
            probe,
        )

        if first_match:
            day, month, year = map(
                int,
                first_match.groups(),
            )

            return self._safe_datetime(
                year=year,
                month=month,
                day=day,
            )

        second_match = re.search(
            numeric_patterns[1],
            probe,
        )

        if second_match:
            year, month, day = map(
                int,
                second_match.groups(),
            )

            return self._safe_datetime(
                year=year,
                month=month,
                day=day,
            )

        month_match = re.search(
            (
                r"\b(\d{1,2})\s+"
                r"(January|February|March|April|May|June|"
                r"July|August|September|October|November|"
                r"December)\s+(\d{4})\b"
            ),
            probe,
            flags=re.IGNORECASE,
        )

        if month_match:
            day = int(month_match.group(1))
            month_name = month_match.group(2)
            year = int(month_match.group(3))

            try:
                parsed = datetime.strptime(
                    f"{day} {month_name} {year}",
                    "%d %B %Y",
                )
            except ValueError:
                return None

            return parsed.replace(tzinfo=timezone.utc)

        return None

    @staticmethod
    def _extract_reference_number(
        candidate: TenderSourceCandidate,
    ) -> str | None:
        probe = (
            f"{candidate.title}\n"
            f"{candidate.text[:1000]}"
        )

        match = re.search(
            (
                r"\b(?:corrigendum|addendum|amendment|"
                r"clarification)"
                r"\s*(?:no\.?|number|#)?"
                r"\s*[:\-]?\s*"
                r"([A-Za-z0-9][A-Za-z0-9/_\-\.]{0,50})"
            ),
            probe,
            flags=re.IGNORECASE,
        )

        if match is None:
            return None

        return match.group(1).strip()

    @staticmethod
    def _safe_datetime(
        *,
        year: int,
        month: int,
        day: int,
    ) -> datetime | None:
        try:
            return datetime(
                year,
                month,
                day,
                tzinfo=timezone.utc,
            )
        except ValueError:
            return None

    @staticmethod
    def _amendment_sort_key(
        candidate: TenderSourceCandidate,
        issued_at: datetime | None,
    ) -> tuple:
        return (
            issued_at is None,
            issued_at or datetime.max.replace(
                tzinfo=timezone.utc
            ),
            candidate.sequence_number,
            str(candidate.logical_document_id),
        )