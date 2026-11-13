from __future__ import annotations

from uuid import UUID

from langgraph.runtime import Runtime

from app.tender_agent.context import (
    TenderRuntimeContext,
)
from app.tender_agent.repositories.normalization_repository import (
    NormalizationRepository,
)
from app.tender_agent.state import TenderAgentState


def normalization_node(
    state: TenderAgentState,
    runtime: Runtime[TenderRuntimeContext],
) -> TenderAgentState:
    service = runtime.context.get(
        "normalization_service"
    )

    if service is None:
        return {
            "normalization_completed": False,
            "workflow_status": "failed",
            "current_node": "normalization",
            "next_action": "mark_failed",
            "errors": [
                "Normalization service is unavailable."
            ],
        }

    session_factory = runtime.context[
        "session_factory"
    ]
    tenant_id = runtime.context["tenant_id"]

    try:
        understanding_run_id = UUID(
            state["field_understanding_run_id"]
        )

        with session_factory() as session:
            repository = NormalizationRepository(
                session
            )

            source_run, source_fields = (
                repository.load_source_fields(
                    understanding_run_id=(
                        understanding_run_id
                    ),
                    tenant_id=tenant_id,
                )
            )

        result = service.normalize(
            fields=source_fields
        )

        with session_factory() as session:
            repository = NormalizationRepository(
                session
            )

            run = repository.replace_normalization(
                tender_version_id=(
                    source_run.tender_version_id
                ),
                understanding_run_id=(
                    understanding_run_id
                ),
                result=result,
                default_currency=(
                    service.default_currency
                ),
                default_timezone=(
                    service.default_timezone
                ),
            )

            session.commit()

    except Exception as exc:
        return {
            "normalization_completed": False,
            "workflow_status": "failed",
            "current_node": "normalization",
            "next_action": "mark_failed",
            "errors": [
                f"Normalization failed: {exc}"
            ],
        }

    return {
        "normalization_completed": True,
        "normalization_run_id": str(run.id),
        "normalized_field_count": (
            result.normalized_field_count
        ),
        "unavailable_field_count": (
            result.unavailable_field_count
        ),
        "normalization_candidate_count": (
            result.candidate_count
        ),
        "normalization_error_count": (
            result.normalization_error_count
        ),
        "normalization_review_field_keys": (
            result.review_field_keys
        ),
        "workflow_status": "normalized",
        "current_node": "normalization",
        "next_action": "reconciliation",
        "warnings": result.warnings,
    }