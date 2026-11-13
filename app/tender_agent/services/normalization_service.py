from __future__ import annotations

import json
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from app.tender_agent.domain.values import (
    NormalizationBuildResult,
    NormalizedCandidateDraft,
    NormalizedFieldDraft,
    SourceFieldEvidence,
    SourceFieldValue,
)


class NormalizationService:
    NUMBER_WORDS = {
        "zero": 0,
        "one": 1,
        "two": 2,
        "three": 3,
        "four": 4,
        "five": 5,
        "six": 6,
        "seven": 7,
        "eight": 8,
        "nine": 9,
        "ten": 10,
        "eleven": 11,
        "twelve": 12,
    }

    BOOLEAN_VALUES = {
        "yes": True,
        "true": True,
        "applicable": True,
        "required": True,
        "enabled": True,
        "no": False,
        "false": False,
        "not applicable": False,
        "not required": False,
        "disabled": False,
    }

    MONEY_MULTIPLIERS = {
        None: Decimal("1"),
        "": Decimal("1"),
        "thousand": Decimal("1000"),
        "lakh": Decimal("100000"),
        "lac": Decimal("100000"),
        "crore": Decimal("10000000"),
        "cr": Decimal("10000000"),
        "million": Decimal("1000000"),
        "billion": Decimal("1000000000"),
    }

    def __init__(
        self,
        *,
        default_currency: str = "INR",
        default_timezone: str = "Asia/Kolkata",
    ) -> None:
        self.default_currency = (
            default_currency.strip().upper()
        )
        self.default_timezone = default_timezone
        self.timezone = ZoneInfo(default_timezone)

    def normalize(
        self,
        *,
        fields: list[SourceFieldValue],
    ) -> NormalizationBuildResult:
        normalized_fields: list[
            NormalizedFieldDraft
        ] = []
        warnings: list[str] = []

        for field in fields:
            try:
                normalized_field = self._normalize_field(
                    field
                )
            except Exception as exc:
                warning = (
                    f"{field.field_key}: normalization "
                    f"failed: {exc}"
                )
                warnings.append(warning)

                normalized_field = NormalizedFieldDraft(
                    source_field_result_id=(
                        field.field_result_id
                    ),
                    field_key=field.field_key,
                    section_key=field.section_key,
                    label=field.label,
                    value_type=field.value_type,
                    source_status=field.source_status,
                    source_confidence=field.confidence,
                    source_needs_review=True,
                    status="error",
                    candidates=[],
                    warnings=[warning],
                )

            normalized_fields.append(normalized_field)

        return NormalizationBuildResult(
            fields=normalized_fields,
            normalized_field_count=sum(
                item.status == "normalized"
                for item in normalized_fields
            ),
            unavailable_field_count=sum(
                item.status == "unavailable"
                for item in normalized_fields
            ),
            candidate_count=sum(
                len(item.candidates)
                for item in normalized_fields
            ),
            normalization_error_count=sum(
                item.status == "error"
                for item in normalized_fields
            ),
            review_field_keys=[
                item.field_key
                for item in normalized_fields
                if (
                    item.status == "error"
                    or item.source_needs_review
                    or any(
                        candidate.evidence_match_degraded
                        for candidate in item.candidates
                    )
                )
            ],
            warnings=warnings,
        )

    def _normalize_field(
        self,
        field: SourceFieldValue,
    ) -> NormalizedFieldDraft:
        if (
            field.source_status
            in {"not_found", "error"}
            or field.raw_value is None
        ):
            return NormalizedFieldDraft(
                source_field_result_id=(
                    field.field_result_id
                ),
                field_key=field.field_key,
                section_key=field.section_key,
                label=field.label,
                value_type=field.value_type,
                source_status=field.source_status,
                source_confidence=field.confidence,
                source_needs_review=(
                    field.needs_review
                ),
                status="unavailable",
                candidates=[],
            )

        raw_candidates = self._flatten_raw_value(
            field.raw_value
        )

        candidates: list[NormalizedCandidateDraft] = []
        field_warnings: list[str] = []

        for ordinal, (
            label,
            raw_value,
            explicit_chunk_ids,
        ) in enumerate(raw_candidates):
            (
                normalized_kind,
                normalized_value,
            ) = self._normalize_value(raw_value)

            normalized_key = json.dumps(
                normalized_value,
                ensure_ascii=False,
                sort_keys=True,
                default=str,
            )

            (
                evidence,
                evidence_match_degraded,
            ) = self._match_evidence(
                raw_value=raw_value,
                explicit_chunk_ids=explicit_chunk_ids,
                evidence=field.evidence,
            )

            best_evidence = self._best_evidence(
                evidence
            )

            if evidence_match_degraded:
                field_warnings.append(
                    f"Candidate {ordinal + 1} could not "
                    "be matched to precise evidence."
                )

            candidates.append(
                NormalizedCandidateDraft(
                    ordinal=ordinal,
                    label=label,
                    raw_value=raw_value,
                    normalized_kind=normalized_kind,
                    normalized_value=normalized_value,
                    normalized_key=normalized_key,
                    confidence=field.confidence,
                    binding_status=(
                        best_evidence.binding_status
                        if best_evidence
                        else None
                    ),
                    source_role=(
                        best_evidence.source_role
                        if best_evidence
                        else None
                    ),
                    precedence_order=(
                        best_evidence.precedence_order
                        if best_evidence
                        else None
                    ),
                    retrieval_score=(
                        best_evidence.retrieval_score
                        if best_evidence
                        else None
                    ),
                    evidence_match_degraded=(
                        evidence_match_degraded
                    ),
                    evidence_ids=[
                        item.evidence_id
                        for item in evidence
                    ],
                )
            )

        return NormalizedFieldDraft(
            source_field_result_id=field.field_result_id,
            field_key=field.field_key,
            section_key=field.section_key,
            label=field.label,
            value_type=field.value_type,
            source_status=field.source_status,
            source_confidence=field.confidence,
            source_needs_review=field.needs_review,
            status=(
                "normalized"
                if candidates
                else "unavailable"
            ),
            candidates=candidates,
            warnings=field_warnings,
        )

    def _flatten_raw_value(
        self,
        raw_value: Any,
    ) -> list[
        tuple[str | None, Any, set[UUID]]
    ]:
        if isinstance(raw_value, list):
            flattened: list[
                tuple[str | None, Any, set[UUID]]
            ] = []

            for item in raw_value:
                flattened.extend(
                    self._flatten_raw_value(item)
                )

            return flattened

        if isinstance(raw_value, dict):
            if "value" in raw_value:
                explicit_ids = self._parse_chunk_ids(
                    raw_value.get(
                        "evidence_chunk_ids",
                        [],
                    )
                )

                return [
                    (
                        self._clean_optional_label(
                            raw_value.get("label")
                        ),
                        raw_value["value"],
                        explicit_ids,
                    )
                ]

            return [
                (
                    self._clean_optional_label(key),
                    value,
                    set(),
                )
                for key, value in raw_value.items()
            ]

        if isinstance(raw_value, str):
            label, value = self._split_label(
                raw_value
            )

            return [(label, value, set())]

        return [(None, raw_value, set())]

    def _normalize_value(
        self,
        value: Any,
    ) -> tuple[str, Any]:
        if isinstance(value, bool):
            return "boolean", value

        if isinstance(value, int | float):
            return "number", value

        if not isinstance(value, str):
            return "structured", value

        cleaned = self._clean_text(value)
        folded = cleaned.casefold()

        if folded in self.BOOLEAN_VALUES:
            return (
                "boolean",
                self.BOOLEAN_VALUES[folded],
            )

        percentage = self._normalize_percentage(
            cleaned
        )

        if percentage is not None:
            return "percentage", percentage

        money = self._normalize_money(cleaned)

        if money is not None:
            return "money", money

        date_value = self._normalize_datetime(cleaned)

        if date_value is not None:
            return date_value

        duration = self._normalize_duration(cleaned)

        if duration is not None:
            return "duration", duration

        return "text", cleaned

    def _normalize_percentage(
        self,
        value: str,
    ) -> dict[str, str] | None:
        match = re.fullmatch(
            r"\s*(-?\d+(?:\.\d+)?)\s*"
            r"(?:%|percent|percentage)\s*",
            value,
            flags=re.IGNORECASE,
        )

        if match is None:
            return None

        number = Decimal(match.group(1))

        return {
            "value": self._decimal_string(number),
            "unit": "percent",
        }

    def _normalize_money(
        self,
        value: str,
    ) -> dict[str, str] | None:
        match = re.fullmatch(
            (
                r"\s*(₹|rs\.?|inr)?\s*"
                r"([\d,]+(?:\.\d+)?)\s*"
                r"(thousand|lakh|lac|crore|cr|"
                r"million|billion)?"
                r"(?:\s*(.*?))?\s*"
            ),
            value,
            flags=re.IGNORECASE,
        )

        if match is None:
            return None

        currency_marker = (
            match.group(1) or ""
        ).casefold()

        multiplier_name = (
            match.group(3) or ""
        ).casefold()

        if not currency_marker and not multiplier_name:
            return None

        try:
            number = Decimal(
                match.group(2).replace(",", "")
            )
        except InvalidOperation:
            return None

        amount = (
            number
            * self.MONEY_MULTIPLIERS[
                multiplier_name
            ]
        )

        qualifier = (
            match.group(4) or ""
        ).strip()

        normalized = {
            "amount": self._decimal_string(amount),
            "currency": self.default_currency,
        }

        if qualifier:
            normalized["qualifier"] = qualifier

        return normalized

    def _normalize_datetime(
        self,
        value: str,
    ) -> tuple[str, dict[str, str]] | None:
        normalized = re.sub(
            r"\bIST\b",
            "",
            value,
            flags=re.IGNORECASE,
        ).strip()

        normalized = re.sub(
            r"\s+at\s+",
            " ",
            normalized,
            flags=re.IGNORECASE,
        )

        formats = [
            ("%d/%m/%Y %I:%M %p", True),
            ("%d-%m-%Y %I:%M %p", True),
            ("%d/%m/%Y %H:%M", True),
            ("%d-%m-%Y %H:%M", True),
            ("%d %B %Y %I:%M %p", True),
            ("%d %b %Y %I:%M %p", True),
            ("%d/%m/%Y", False),
            ("%d-%m-%Y", False),
            ("%Y-%m-%d", False),
            ("%d %B %Y", False),
            ("%d %b %Y", False),
        ]

        for date_format, has_time in formats:
            try:
                parsed = datetime.strptime(
                    normalized,
                    date_format,
                )
            except ValueError:
                continue

            if has_time:
                aware = parsed.replace(
                    tzinfo=self.timezone
                )

                return (
                    "datetime",
                    {
                        "value": aware.isoformat(),
                        "timezone": (
                            self.default_timezone
                        ),
                    },
                )

            return (
                "date",
                {
                    "value": parsed.date().isoformat()
                },
            )

        return None

    def _normalize_duration(
        self,
        value: str,
    ) -> dict[str, Any] | None:
        match = re.fullmatch(
            (
                r"\s*(\d+|[A-Za-z]+)\s+"
                r"(day|days|week|weeks|month|months|"
                r"year|years)\s*"
            ),
            value,
            flags=re.IGNORECASE,
        )

        if match is None:
            return None

        raw_number = match.group(1).casefold()

        if raw_number.isdigit():
            amount = int(raw_number)
        else:
            amount = self.NUMBER_WORDS.get(raw_number)

        if amount is None:
            return None

        unit = match.group(2).casefold().rstrip("s")

        return {
            "value": amount,
            "unit": unit,
        }

    def _match_evidence(
        self,
        *,
        raw_value: Any,
        explicit_chunk_ids: set[UUID],
        evidence: list[SourceFieldEvidence],
    ) -> tuple[list[SourceFieldEvidence], bool]:
        if explicit_chunk_ids:
            matches = [
                item
                for item in evidence
                if item.chunk_id in explicit_chunk_ids
            ]

            return matches, not bool(matches)

        candidate_tokens = self._significant_tokens(
            str(raw_value)
        )

        matches = []

        for item in evidence:
            quote_tokens = self._significant_tokens(
                item.quote
            )

            if not candidate_tokens:
                continue

            overlap = (
                len(candidate_tokens & quote_tokens)
                / len(candidate_tokens)
            )

            if overlap >= 0.50:
                matches.append(item)

        if matches:
            return matches, False

        # Preserve all evidence, but mark the match as degraded.
        return list(evidence), True

    def _best_evidence(
        self,
        evidence: list[SourceFieldEvidence],
    ) -> SourceFieldEvidence | None:
        if not evidence:
            return None

        return max(
            evidence,
            key=lambda item: (
                self._binding_rank(
                    item.binding_status
                ),
                self._role_rank(item.source_role),
                item.precedence_order,
                item.retrieval_score,
            ),
        )

    @staticmethod
    def _binding_rank(value: str) -> int:
        return {
            "binding": 3,
            "review_required": 2,
            "non_binding": 1,
        }.get(value, 0)

    @staticmethod
    def _role_rank(value: str) -> int:
        return {
            "corrigendum": 5,
            "prebid_clarification": 4,
            "primary_base": 3,
            "base_supporting": 2,
            "reference": 1,
        }.get(value, 0)

    @staticmethod
    def _split_label(
        value: str,
    ) -> tuple[str | None, str]:
        match = re.fullmatch(
            r"\s*([^:\n]{2,100})\s*:\s*(.+)\s*",
            value,
            flags=re.DOTALL,
        )

        if match is None:
            return None, value.strip()

        return (
            match.group(1).strip(),
            match.group(2).strip(),
        )

    @staticmethod
    def _parse_chunk_ids(
        values: Any,
    ) -> set[UUID]:
        if not isinstance(values, list):
            return set()

        parsed: set[UUID] = set()

        for value in values:
            try:
                parsed.add(UUID(str(value)))
            except (TypeError, ValueError):
                continue

        return parsed

    @staticmethod
    def _clean_optional_label(
        value: Any,
    ) -> str | None:
        if not isinstance(value, str):
            return None

        cleaned = value.strip()

        return cleaned or None

    @staticmethod
    def _clean_text(value: str) -> str:
        return re.sub(r"\s+", " ", value).strip()

    @staticmethod
    def _significant_tokens(
        value: str,
    ) -> set[str]:
        return {
            token
            for token in re.findall(
                r"[A-Za-z0-9]+",
                value.casefold(),
            )
            if len(token) >= 2
        }

    @staticmethod
    def _decimal_string(
        value: Decimal,
    ) -> str:
        normalized = format(
            value.normalize(),
            "f",
        )

        if "." in normalized:
            normalized = normalized.rstrip("0").rstrip(".")

        return normalized or "0"