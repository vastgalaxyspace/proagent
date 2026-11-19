from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable
from uuid import UUID

from langgraph.runtime import Runtime
from langgraph.types import interrupt

from app.tender_agent.context import TenderRuntimeContext
from app.tender_agent.domain.statuses import OperationStatus
from app.tender_agent.repositories.operation_repository import (
    OperationRepository,
)
from app.tender_agent.state import TenderAgentState
from app.infrastructure.providers.usage import current_ai_usage


def _check_operation_control(
    *,
    node_name: str,
    state: TenderAgentState,
    runtime: Runtime[TenderRuntimeContext],
) -> None:
    """Apply pause/cancel requests before starting a graph node."""

    operation_id = state.get("operation_id")
    session_factory = runtime.context.get("session_factory")
    tenant_id = runtime.context.get("tenant_id")

    if not operation_id or session_factory is None or not tenant_id:
        return

    control_kind: str | None = None

    with session_factory() as session:
        repository = OperationRepository(session)
        operation = repository.get_for_tenant(
            operation_id=UUID(str(operation_id)),
            tenant_id=str(tenant_id),
            for_update=True,
        )

        if operation is None:
            return

        repository.touch_heartbeat(operation)

        if operation.status in {
            OperationStatus.PAUSE_REQUESTED.value,
            OperationStatus.PAUSED.value,
        }:
            repository.mark_paused(operation)
            control_kind = "operator_pause"
        elif operation.status in {
            OperationStatus.CANCEL_REQUESTED.value,
            OperationStatus.CANCELLED.value,
        }:
            repository.mark_cancelled(operation)
            control_kind = "operator_cancel"

        session.commit()

    if control_kind is not None:
        interrupt(
            {
                "type": control_kind,
                "node": node_name,
                "operation_id": str(operation_id),
            }
        )
        return

    if runtime.context.get("resuming_operator_pause"):
        runtime.context["resuming_operator_pause"] = False
        interrupt(
            {
                "type": "operator_pause",
                "node": node_name,
                "operation_id": str(operation_id),
            }
        )


def tracked_node(
    node_name: str,
    node: Callable[..., TenderAgentState],
    *,
    uses_runtime: bool = True,
    terminal: bool = False,
) -> Callable[..., TenderAgentState]:
    """Add execution history without changing node business logic."""

    def wrapper(
        state: TenderAgentState,
        runtime: Runtime[TenderRuntimeContext],
    ) -> TenderAgentState:
        _check_operation_control(
            node_name=node_name,
            state=state,
            runtime=runtime,
        )
        started_at = datetime.now(timezone.utc)

        if uses_runtime:
            result = node(state, runtime)
        else:
            result = node(state)

        finished_at = datetime.now(timezone.utc)
        update = dict(result)
        node_failed = (
            update.get("workflow_status") == "failed"
            and not terminal
        )

        events: list[dict[str, Any]] = [
            {
                "node": node_name,
                "status": (
                    "failed" if node_failed else "completed"
                ),
                "started_at": started_at.isoformat(),
                "finished_at": finished_at.isoformat(),
                "next_node": update.get("next_action"),
                "message": (
                    f"{node_name} failed."
                    if node_failed
                    else f"{node_name} completed."
                ),
            }
        ]

        for skipped_node in update.get(
            "skipped_nodes",
            [],
        ):
            events.append(
                {
                    "node": skipped_node,
                    "status": "skipped",
                    "started_at": finished_at.isoformat(),
                    "finished_at": finished_at.isoformat(),
                    "next_node": update.get("next_action"),
                    "message": (
                        f"{skipped_node} was skipped by "
                        "a conditional edge."
                    ),
                }
            )

        update["node_events"] = events
        problem_events: list[dict[str, Any]] = []
        for severity, key in (
            ("warning", "warnings"),
            ("error", "errors"),
        ):
            for message in update.get(key, []):
                problem_events.append(
                    {
                        "node": node_name,
                        "severity": severity,
                        "message": str(message),
                        "recorded_at": finished_at.isoformat(),
                    }
                )
        update["problem_events"] = problem_events
        ai_usage = current_ai_usage()
        if ai_usage is not None:
            update["ai_usage"] = ai_usage

        if node_failed:
            update["failed_node"] = node_name
        else:
            update["completed_nodes"] = [node_name]

        return update

    return wrapper
