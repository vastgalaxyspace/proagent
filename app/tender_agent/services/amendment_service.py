from __future__ import annotations

import json
import re
from datetime import datetime, timezone

from app.infrastructure.providers.llm import LLMProvider

from app.tender_agent.domain.authority import (
    AmendmentOperationDraft,
    BaseTenderSelection,
    EffectiveTenderPlanDraft,
    SourcePlanMemberDraft,
    TenderSourceCandidate,
)
from app.tender_agent.schemas.amendments import (
    LLMAmendmentBatch,
)
from app.tender_agent.schemas.field_schema import (
    TenderFieldCatalog,
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

    def __init__(
        self,
        *,
        llm: LLMProvider | None = None,
        field_catalog: TenderFieldCatalog | None = None,
        minimum_confidence: float = 0.70,
        max_source_characters: int = 30_000,
    ) -> None:
        self.llm = llm
        self.field_catalog = field_catalog
        self.minimum_confidence = minimum_confidence
        self.max_source_characters = max_source_characters

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

        authoritative_ids = set(
            selection.authoritative_logical_document_ids
        )
        if not authoritative_ids:
            authoritative_ids = {
                selection.primary_logical_document_id,
                *selection.supporting_logical_document_ids,
            }

        base_candidates = [
            candidate
            for candidate in candidates
            if (
                candidate.logical_document_id
                in authoritative_ids
                and candidate.document_type
                not in {
                    "corrigendum",
                    "prebid_clarification",
                }
            )
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

        reference_candidates = [
            candidate
            for candidate in candidates
            if (
                candidate.content_role == "reference"
                and candidate.document_type
                not in {
                    "corrigendum",
                    "prebid_clarification",
                }
            )
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
            *reference_candidates,
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

        operations, operation_warnings = (
            self._extract_semantic_operations(
                candidates=post_base_candidates,
                members=members,
            )
        )
        warnings.extend(operation_warnings)

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
            operations=operations,
            needs_review=needs_review,
            warnings=warnings,
        )

    def _extract_semantic_operations(
        self,
        *,
        candidates: list[TenderSourceCandidate],
        members: list[SourcePlanMemberDraft],
    ) -> tuple[list[AmendmentOperationDraft], list[str]]:
        if not candidates:
            return [], []

        if self.llm is None:
            return [], [
                "Amendment documents were ordered, but semantic "
                "amendment extraction was unavailable because the "
                "LLM provider is disabled."
            ]

        member_by_document = {
            member.logical_document_id: member
            for member in members
        }
        operations: list[AmendmentOperationDraft] = []
        warnings: list[str] = []

        for candidate in candidates:
            member = member_by_document.get(
                candidate.logical_document_id
            )
            if member is None:
                continue

            try:
                extracted, candidate_warnings = (
                    self._extract_candidate_operations(
                        candidate=candidate,
                        binding_status=member.binding_status,
                    )
                )
                operations.extend(extracted)
                warnings.extend(candidate_warnings)
            except Exception as exc:
                warnings.append(
                    f"{candidate.title}: semantic amendment "
                    f"extraction failed: {str(exc)[:300]}"
                )

        return operations, warnings

    def _extract_candidate_operations(
        self,
        *,
        candidate: TenderSourceCandidate,
        binding_status: str,
    ) -> tuple[list[AmendmentOperationDraft], list[str]]:
        remaining = self.max_source_characters
        context_pages: list[dict] = []

        for page in candidate.pages:
            if remaining <= 0:
                break
            text = page.text[:remaining]
            remaining -= len(text)
            context_pages.append(
                {
                    "page_id": str(page.page_id),
                    "page_number": page.source_page_number,
                    "text": text,
                }
            )

        payload = self.llm.generate_json(
            system_prompt=(
                "You extract explicit amendment operations from an "
                "official procurement corrigendum, addendum, or pre-bid "
                "clarification. Use only supplied text. Return replace, "
                "add, delete, or clarify operations. Every operation must "
                "identify its target and cite an exact evidence quote and "
                "page_id. When a configured field target matches, use its "
                "field key as the target. Do not infer an amendment from "
                "silence."
            ),
            user_prompt=(
                "Extract amendment operations from this source:\n"
                + json.dumps(
                    {
                        "title": candidate.title,
                        "document_type": candidate.document_type,
                        "configured_field_targets": (
                            [
                                {
                                    "key": field.key,
                                    "label": field.label,
                                    "aliases": (
                                        field.retrieval_guidance.aliases
                                    ),
                                }
                                for _section, field
                                in self.field_catalog.all_fields()
                            ]
                            if self.field_catalog is not None
                            else []
                        ),
                        "pages": context_pages,
                        "output_shape": {
                            "operations": [
                                {
                                    "operation": (
                                        "replace | add | delete | clarify"
                                    ),
                                    "target": "clause, field, or requirement",
                                    "previous_value": None,
                                    "revised_value": None,
                                    "page_id": "UUID",
                                    "evidence_quote": "exact quote",
                                    "confidence": 0.0,
                                    "reason": "short reason",
                                }
                            ]
                        },
                    },
                    ensure_ascii=False,
                    indent=2,
                    default=str,
                )
            ),
            deep=False,
        )
        batch = LLMAmendmentBatch.model_validate(payload)
        page_by_id = {
            page.page_id: page
            for page in candidate.pages
        }
        grounded: list[AmendmentOperationDraft] = []
        warnings: list[str] = []

        for item in batch.operations:
            page = page_by_id.get(item.page_id)

            if page is None or not self._quote_is_supported(
                quote=item.evidence_quote,
                text=page.text if page is not None else "",
            ):
                page = next(
                    (
                        candidate_page
                        for candidate_page in candidate.pages
                        if self._quote_is_supported(
                            quote=item.evidence_quote,
                            text=candidate_page.text,
                        )
                    ),
                    None,
                )

            if page is None:
                warnings.append(
                    f"{candidate.title}: ignored an ungrounded "
                    f"amendment operation for {item.target}."
                )
                continue

            validated = bool(
                binding_status == "binding"
                and item.confidence >= self.minimum_confidence
            )

            if not validated:
                warnings.append(
                    f"{candidate.title}: amendment operation for "
                    f"{item.target} requires human review."
                )

            grounded.append(
                AmendmentOperationDraft(
                    logical_document_id=(
                        candidate.logical_document_id
                    ),
                    page_id=page.page_id,
                    operation=item.operation,
                    target=item.target.strip(),
                    previous_value=item.previous_value,
                    revised_value=item.revised_value,
                    evidence_quote=item.evidence_quote.strip(),
                    confidence=item.confidence,
                    validation_status=(
                        "validated"
                        if validated
                        else "review_required"
                    ),
                    reason=item.reason.strip(),
                )
            )

        return grounded, warnings

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
        return bool(
            normalized_quote
            and normalized_quote in normalize(text)
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
