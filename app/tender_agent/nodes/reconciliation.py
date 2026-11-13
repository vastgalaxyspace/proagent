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


def reconciliation_node(
    state: TenderAgentState,
    runtime: Runtime[TenderRuntimeContext],
) -> TenderAgentState:
    service = runtime.context.get(
        "reconciliation_service"
    )

    if service is None:
        return {
            "reconciliation_completed": False,
            "workflow_status": "failed",
            "current_node": "reconciliation",
            "next_action": "mark_failed",
            "errors": [
                "Reconciliation service is unavailable."
            ],
        }

    session_factory = runtime.context[
        "session_factory"
    ]
    tenant_id = runtime.context["tenant_id"]

    try:
        normalization_run_id = UUID(
            state["normalization_run_id"]
        )

        with session_factory() as session:
            repository = NormalizationRepository(
                session
            )

            run = repository.get_run(
                normalization_run_id=(
                    normalization_run_id
                ),
                tenant_id=tenant_id,
            )

            if run is None:
                raise ValueError(
                    "Normalization run was not found."
                )

            fields = (
                repository.load_normalized_fields(
                    normalization_run_id=(
                        normalization_run_id
                    )
                )
            )

        result = service.reconcile(
            fields=fields
        )

        with session_factory() as session:
            repository = NormalizationRepository(
                session
            )

            stored_run = repository.get_run(
                normalization_run_id=(
                    normalization_run_id
                ),
                tenant_id=tenant_id,
            )

            if stored_run is None:
                raise ValueError(
                    "Normalization run disappeared."
                )

            repository.apply_reconciliation(
                run=stored_run,
                result=result,
            )

            session.commit()

    except Exception as exc:
        return {
            "reconciliation_completed": False,
            "workflow_status": "failed",
            "current_node": "reconciliation",
            "next_action": "mark_failed",
            "errors": [
                f"Reconciliation failed: {exc}"
            ],
        }

    return {
        "reconciliation_completed": True,
        "reconciled_field_count": (
            result.reconciled_field_count
        ),
        "conflict_field_count": (
            result.conflict_field_count
        ),
        "unresolved_field_count": (
            result.unresolved_field_count
        ),
        "conflict_field_keys": (
            result.conflict_field_keys
        ),
        "reconciliation_review_field_keys": (
            result.review_field_keys
        ),
        "workflow_status": "reconciled",
        "current_node": "reconciliation",
        "next_action": "mark_ready",
        "warnings": result.warnings,
    }
