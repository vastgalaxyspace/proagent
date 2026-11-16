from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import BackgroundTasks
from sqlalchemy.orm import Session, sessionmaker

from app.infrastructure.queue.worker import execute_tender_run


def dispatch_tender_run(
    *,
    background_tasks: BackgroundTasks,
    operation_id: UUID,
    tenant_id: str,
    user_id: str,
    graph: Any,
    graph_config: dict[str, Any],
    graph_input: Any,
    runtime_context: dict[str, Any],
    session_factory: sessionmaker[Session],
) -> None:
    background_tasks.add_task(
        execute_tender_run,
        operation_id=operation_id,
        tenant_id=tenant_id,
        user_id=user_id,
        graph=graph,
        graph_config=graph_config,
        graph_input=graph_input,
        runtime_context=runtime_context,
        session_factory=session_factory,
    )
