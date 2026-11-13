from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.infrastructure.database.models import (
    TenderFinalizationIssue,
    TenderFinalizationRun,
)
from app.tender_agent.schemas.finalization import TenderProfilePayload
from app.tender_agent.schemas.review import ReviewCorrection


class HandoffService:
    _field_patch_keys = {
        "status",
        "effective_value",
        "effective_display_value",
        "needs_review",
        "conflict_reason",
    }
    _requirement_patch_keys = {
        "title",
        "requirement_text",
        "obligation_level",
        "condition_text",
        "bidder_proof",
        "validation_status",
        "needs_review",
    }

    def build_package(
        self,
        *,
        finalization: TenderFinalizationRun,
        issues: list[TenderFinalizationIssue],
    ) -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "finalization_run_id": str(finalization.id),
            "tender_version_id": str(finalization.tender_version_id),
            "validation_status": finalization.status,
            "readiness_score": finalization.readiness_score,
            "summary": finalization.summary,
            "review_reasons": list(finalization.review_reasons_json),
            "coverage_metrics": dict(finalization.coverage_metrics_json),
            "profile": deepcopy(finalization.profile_json),
            "issues": [
                {
                    "code": issue.code,
                    "severity": issue.severity,
                    "category": issue.category,
                    "entity_type": issue.entity_type,
                    "entity_key": issue.entity_key,
                    "message": issue.message,
                    "requires_review": issue.requires_review,
                    "fatal": issue.fatal,
                }
                for issue in issues
            ],
        }

    def apply_corrections(
        self,
        *,
        profile: dict[str, Any],
        corrections: list[ReviewCorrection],
    ) -> dict[str, Any]:
        corrected = deepcopy(profile)
        fields = {
            item["field_key"]: item
            for item in corrected.get("fields", [])
        }
        requirements = {
            item["requirement_code"]: item
            for item in corrected.get("requirements", [])
        }

        for correction in corrections:
            if correction.target_type == "field":
                target = fields.get(correction.target_key)
                allowed = self._field_patch_keys
            else:
                target = requirements.get(correction.target_key)
                allowed = self._requirement_patch_keys

            if target is None:
                raise ValueError(
                    f"Review target was not found: {correction.target_type} "
                    f"'{correction.target_key}'."
                )

            unsupported = set(correction.patch) - allowed
            if unsupported:
                names = ", ".join(sorted(unsupported))
                raise ValueError(
                    f"Unsupported {correction.target_type} correction keys: {names}."
                )
            target.update(deepcopy(correction.patch))

        validated = TenderProfilePayload.model_validate(corrected)
        return validated.model_dump(mode="json")
