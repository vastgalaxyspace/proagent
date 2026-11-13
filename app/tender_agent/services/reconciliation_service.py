from __future__ import annotations

import json
import re
from collections import defaultdict
from typing import Any

from app.tender_agent.domain.values import (
    NormalizedCandidateDraft,
    NormalizedFieldDraft,
    ReconciledCandidateDraft,
    ReconciledFieldDraft,
    ReconciliationBuildResult,
)


class ReconciliationService:
    def __init__(
        self,
        *,
        minimum_confidence: float = 0.65,
    ) -> None:
        if not 0.0 <= minimum_confidence <= 1.0:
            raise ValueError(
                "Reconciliation confidence must be "
                "between 0 and 1."
            )

        self.minimum_confidence = minimum_confidence

    def reconcile(
        self,
        *,
        fields: list[NormalizedFieldDraft],
    ) -> ReconciliationBuildResult:
        results = [
            self._reconcile_field(field)
            for field in fields
        ]

        conflict_keys = [
            result.field_key
            for result in results
            if result.status == "conflict"
        ]

        review_keys = [
            result.field_key
            for result in results
            if result.needs_review
        ]

        return ReconciliationBuildResult(
            fields=results,
            reconciled_field_count=sum(
                result.status == "reconciled"
                for result in results
            ),
            conflict_field_count=len(conflict_keys),
            unresolved_field_count=sum(
                result.status
                in {"unavailable", "error"}
                for result in results
            ),
            conflict_field_keys=conflict_keys,
            review_field_keys=review_keys,
            warnings=[
                (
                    f"{result.field_key}: "
                    f"{result.conflict_reason}"
                )
                for result in results
                if result.conflict_reason
            ],
        )

    def _reconcile_field(
        self,
        field: NormalizedFieldDraft,
    ) -> ReconciledFieldDraft:
        if field.status != "normalized":
            return ReconciledFieldDraft(
                field_key=field.field_key,
                status=field.status,
                effective_value=None,
                effective_display_value=None,
                needs_review=True,
                conflict_reason=(
                    "No normalized candidates were "
                    "available."
                ),
                candidate_decisions=[],
            )

        groups: dict[
            str,
            list[NormalizedCandidateDraft],
        ] = defaultdict(list)

        for candidate in field.candidates:
            groups[
                self._group_key(
                    candidate,
                    source_status=field.source_status,
                )
            ].append(candidate)

        decisions: dict[
            int,
            ReconciledCandidateDraft,
        ] = {}

        effective_items: list[dict[str, Any]] = []
        conflict_reasons: list[str] = []

        for group_candidates in groups.values():
            (
                selected,
                group_decisions,
                conflict_reason,
            ) = self._resolve_group(group_candidates)

            for decision in group_decisions:
                decisions[decision.ordinal] = decision

            if conflict_reason:
                conflict_reasons.append(
                    conflict_reason
                )
                continue

            if selected is not None:
                effective_items.append(
                    {
                        "label": selected.label,
                        "kind": (
                            selected.normalized_kind
                        ),
                        "value": (
                            selected.normalized_value
                        ),
                        "raw_value": (
                            selected.raw_value
                        ),
                    }
                )

        has_conflict = bool(conflict_reasons)

        selected_candidates = [
            candidate
            for candidate in field.candidates
            if decisions.get(candidate.ordinal)
            and decisions[candidate.ordinal].selected
        ]

        weak_selected_candidate = any(
            candidate.confidence
            < self.minimum_confidence
            or candidate.evidence_match_degraded
            or candidate.binding_status
            in {None, "review_required"}
            for candidate in selected_candidates
        )

        effective_value = (
            None
            if has_conflict
            else self._effective_value(
                effective_items
            )
        )

        return ReconciledFieldDraft(
            field_key=field.field_key,
            status=(
                "conflict"
                if has_conflict
                else "reconciled"
            ),
            effective_value=effective_value,
            effective_display_value=(
                None
                if effective_value is None
                else json.dumps(
                    effective_value,
                    ensure_ascii=False,
                    default=str,
                )
            ),
            needs_review=(
                has_conflict
                or weak_selected_candidate
                or (
                    field.source_needs_review
                    and field.source_status != "ambiguous"
                )
            ),
            conflict_reason=(
                "; ".join(conflict_reasons)
                if conflict_reasons
                else None
            ),
            candidate_decisions=[
                decisions[candidate.ordinal]
                for candidate in field.candidates
            ],
        )

    def _resolve_group(
        self,
        candidates: list[NormalizedCandidateDraft],
    ) -> tuple[
        NormalizedCandidateDraft | None,
        list[ReconciledCandidateDraft],
        str | None,
    ]:
        ordered = sorted(
            candidates,
            key=self._authority_key,
            reverse=True,
        )

        normalized_keys = {
            candidate.normalized_key
            for candidate in ordered
        }

        if len(normalized_keys) == 1:
            selected = ordered[0]

            return (
                selected,
                [
                    ReconciledCandidateDraft(
                        ordinal=candidate.ordinal,
                        selected=(
                            candidate.ordinal
                            == selected.ordinal
                        ),
                        resolution_status=(
                            "selected"
                            if candidate.ordinal
                            == selected.ordinal
                            else "equivalent"
                        ),
                        resolution_reason=(
                            "Equivalent normalized value; "
                            "highest-authority evidence selected."
                        ),
                    )
                    for candidate in ordered
                ],
                None,
            )

        selected = ordered[0]
        second = ordered[1]

        selected_authority = self._legal_authority_key(
            selected
        )
        second_authority = self._legal_authority_key(
            second
        )

        if (
            selected.binding_status == "binding"
            and selected_authority > second_authority
        ):
            return (
                selected,
                [
                    ReconciledCandidateDraft(
                        ordinal=candidate.ordinal,
                        selected=(
                            candidate.ordinal
                            == selected.ordinal
                        ),
                        resolution_status=(
                            "selected"
                            if candidate.ordinal
                            == selected.ordinal
                            else "overridden"
                        ),
                        resolution_reason=(
                            "Higher-authority binding "
                            "source selected."
                        ),
                    )
                    for candidate in ordered
                ],
                None,
            )

        label = selected.label or "unlabelled value"

        return (
            None,
            [
                ReconciledCandidateDraft(
                    ordinal=candidate.ordinal,
                    selected=False,
                    resolution_status="conflict",
                    resolution_reason=(
                        "Different values have equal or "
                        "uncertain authority."
                    ),
                )
                for candidate in ordered
            ],
            (
                f"Unresolved conflict for {label}: "
                "different candidates have equal or "
                "uncertain authority."
            ),
        )

    def _authority_key(
        self,
        candidate: NormalizedCandidateDraft,
    ) -> tuple[int, int, int, float]:
        return (
            self._binding_rank(
                candidate.binding_status
            ),
            self._role_rank(candidate.source_role),
            (
                candidate.precedence_order
                if candidate.precedence_order is not None
                else -1
            ),
            candidate.retrieval_score or 0.0,
        )

    def _legal_authority_key(
        self,
        candidate: NormalizedCandidateDraft,
    ) -> tuple[int, int, int]:
        """Return only legal/source precedence dimensions.

        Retrieval relevance is useful for ordering equivalent
        evidence, but it must never decide which conflicting legal
        value becomes effective.
        """
        return (
            self._binding_rank(candidate.binding_status),
            self._role_rank(candidate.source_role),
            (
                candidate.precedence_order
                if candidate.precedence_order is not None
                else -1
            ),
        )

    def _group_key(
        self,
        candidate: NormalizedCandidateDraft,
        *,
        source_status: str,
    ) -> str:
        if candidate.label:
            return re.sub(
                r"\s+",
                " ",
                candidate.label.casefold(),
            ).strip()

        if source_status == "ambiguous":
            return "__ambiguous_unlabelled__"

        # Different unlabelled list values are normally separate
        # legitimate items, not conflicts.
        return (
            "__unlabelled__:"
            f"{candidate.normalized_key}"
        )

    @staticmethod
    def _effective_value(
        items: list[dict[str, Any]],
    ) -> Any:
        if len(items) == 1:
            return items[0]["value"]

        return items

    @staticmethod
    def _binding_rank(
        value: str | None,
    ) -> int:
        return {
            "binding": 3,
            "review_required": 2,
            "non_binding": 1,
        }.get(value, 0)

    @staticmethod
    def _role_rank(
        value: str | None,
    ) -> int:
        return {
            "corrigendum": 5,
            "prebid_clarification": 4,
            "primary_base": 3,
            "base_supporting": 2,
            "reference": 1,
        }.get(value, 0)
