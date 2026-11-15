from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from langgraph.runtime import Runtime

from app.tender_agent.context import TenderRuntimeContext
from app.tender_agent.state import TenderAgentState


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

        if node_failed:
            update["failed_node"] = node_name
        else:
            update["completed_nodes"] = [node_name]

        return update

    return wrapper
