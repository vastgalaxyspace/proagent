from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.infrastructure.database.models import Operation
from app.tender_agent.domain.statuses import OperationStatus


class OperationRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_operation(
        self,
        *,
        tenant_id: str,
        tender_version_id: UUID,
        request_id: str,
        thread_id: str,
    ) -> Operation:
        operation = Operation(
            tenant_id=tenant_id,
            tender_version_id=tender_version_id,
            request_id=request_id,
            thread_id=thread_id,
            stage="tender_understanding",
            status=OperationStatus.QUEUED.value,
        )

        self.session.add(operation)
        self.session.flush()

        return operation

    def get_for_tenant(
        self,
        *,
        operation_id: UUID,
        tenant_id: str,
    ) -> Operation | None:
        statement: Select[tuple[Operation]] = select(Operation).where(
            Operation.id == operation_id,
            Operation.tenant_id == tenant_id,
        )

        return self.session.scalar(statement)

    def get_by_thread(
        self,
        *,
        thread_id: str,
        tenant_id: str,
    ) -> Operation | None:
        statement: Select[tuple[Operation]] = select(Operation).where(
            Operation.thread_id == thread_id,
            Operation.tenant_id == tenant_id,
        )

        return self.session.scalar(statement)

    def mark_running(self, operation: Operation) -> None:
        operation.status = OperationStatus.RUNNING.value
        operation.attempt += 1
        operation.started_at = datetime.now(timezone.utc)
        operation.error_code = None
        operation.error_detail = None

    def mark_succeeded(
        self,
        operation: Operation,
        *,
        result: dict[str, Any],
    ) -> None:
        operation.status = OperationStatus.SUCCEEDED.value
        operation.result_json = result
        operation.finished_at = datetime.now(timezone.utc)
        operation.error_code = None
        operation.error_detail = None

    def mark_awaiting_review(
        self,
        operation: Operation,
        *,
        result: dict[str, Any],
    ) -> None:
        operation.status = OperationStatus.AWAITING_REVIEW.value
        operation.result_json = result
        operation.finished_at = None
        operation.error_code = None
        operation.error_detail = None

    def mark_review_completed(
        self,
        operation: Operation,
        *,
        decision: str,
        result: dict[str, Any],
    ) -> None:
        allowed = {
            OperationStatus.APPROVED.value,
            OperationStatus.CHANGES_REQUESTED.value,
            OperationStatus.REJECTED.value,
        }
        if decision not in allowed:
            raise ValueError(f"Unsupported review decision: {decision}.")
        operation.status = decision
        operation.result_json = result
        operation.finished_at = datetime.now(timezone.utc)
        operation.error_code = None
        operation.error_detail = None

    def mark_failed(
        self,
        operation: Operation,
        *,
        error_code: str,
        error_detail: str,
        result: dict[str, Any] | None = None,
    ) -> None:
        operation.status = OperationStatus.FAILED.value
        operation.result_json = result
        operation.error_code = error_code
        operation.error_detail = error_detail
        operation.finished_at = datetime.now(timezone.utc)
