from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session, sessionmaker

from app.tender_agent.domain.statuses import OperationStatus
from app.tender_agent.repositories.audit_repository import (
    AuditRepository,
)
from app.tender_agent.repositories.operation_repository import (
    OperationRepository,
)


logger = logging.getLogger(__name__)


def execute_tender_run(
    *,
    operation_id: UUID,
    tenant_id: str,
    user_id: str,
    graph: Any,
    graph_config: dict[str, Any],
    initial_state: dict[str, Any],
    runtime_context: dict[str, Any],
    session_factory: sessionmaker[Session],
) -> None:
    """Execute a committed tender operation outside its HTTP request."""

    with session_factory() as session:
        repository = OperationRepository(session)
        operation = repository.get_for_tenant(
            operation_id=operation_id,
            tenant_id=tenant_id,
        )

        if operation is None:
            logger.error(
                "Tender operation disappeared before execution: %s",
                operation_id,
            )
            return

        if operation.status != OperationStatus.QUEUED.value:
            logger.warning(
                "Tender operation %s was not queued; status=%s",
                operation_id,
                operation.status,
            )
            return

        repository.mark_running(operation)
        session.commit()

    try:
        result = graph.invoke(
            initial_state,
            config=graph_config,
            context=runtime_context,
        )
    except Exception as exc:
        logger.exception(
            "Tender graph execution failed operation_id=%s",
            operation_id,
        )
        _mark_execution_failed(
            operation_id=operation_id,
            tenant_id=tenant_id,
            user_id=user_id,
            error=exc,
            session_factory=session_factory,
        )
        return

    interrupted = bool(result.get("__interrupt__"))
    serializable_result = {
        key: value
        for key, value in result.items()
        if key != "__interrupt__"
    }
    result_summary = jsonable_encoder(
        serializable_result
    )

    if interrupted:
        result_summary["workflow_status"] = "awaiting_review"
        result_summary["current_node"] = "review_handoff"

    with session_factory() as session:
        operation_repository = OperationRepository(session)
        audit_repository = AuditRepository(session)
        operation = operation_repository.get_for_tenant(
            operation_id=operation_id,
            tenant_id=tenant_id,
        )

        if operation is None:
            logger.error(
                "Tender operation disappeared after execution: %s",
                operation_id,
            )
            return

        if result.get("workflow_status") == "failed":
            operation_repository.mark_failed(
                operation,
                error_code="graph_validation_failed",
                error_detail="Tender Agent validation failed.",
                result=result_summary,
            )
            event_type = "tender.understanding.failed"
        elif interrupted:
            operation_repository.mark_awaiting_review(
                operation,
                result=result_summary,
            )
            event_type = "tender.review.awaiting"
        else:
            operation_repository.mark_succeeded(
                operation,
                result=result_summary,
            )
            event_type = "tender.understanding.succeeded"

        audit_repository.record(
            tenant_id=tenant_id,
            actor_user_id=user_id,
            event_type=event_type,
            entity_type="operation",
            entity_id=str(operation.id),
            after=result_summary,
        )
        session.commit()


def _mark_execution_failed(
    *,
    operation_id: UUID,
    tenant_id: str,
    user_id: str,
    error: Exception,
    session_factory: sessionmaker[Session],
) -> None:
    try:
        with session_factory() as session:
            operation_repository = OperationRepository(session)
            audit_repository = AuditRepository(session)
            operation = operation_repository.get_for_tenant(
                operation_id=operation_id,
                tenant_id=tenant_id,
            )

            if operation is None:
                return

            operation_repository.mark_failed(
                operation,
                error_code="graph_execution_failed",
                error_detail=str(error),
            )
            audit_repository.record(
                tenant_id=tenant_id,
                actor_user_id=user_id,
                event_type="tender.understanding.failed",
                entity_type="operation",
                entity_id=str(operation.id),
                after={
                    "error_code": "graph_execution_failed",
                    "error_detail": str(error),
                },
            )
            session.commit()
    except Exception:
        logger.exception(
            "Failed to persist tender execution failure: %s",
            operation_id,
        )
