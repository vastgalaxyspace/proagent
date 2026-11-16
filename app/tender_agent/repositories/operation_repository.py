from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import Select, select, update
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
        for_update: bool = False,
    ) -> Operation | None:
        statement: Select[tuple[Operation]] = select(Operation).where(
            Operation.id == operation_id,
            Operation.tenant_id == tenant_id,
        )

        if for_update:
            statement = statement.with_for_update()
        return self.session.scalar(statement)

    def get_by_thread(
        self,
        *,
        thread_id: str,
        tenant_id: str,
        for_update: bool = False,
    ) -> Operation | None:
        statement: Select[tuple[Operation]] = select(Operation).where(
            Operation.thread_id == thread_id,
            Operation.tenant_id == tenant_id,
        )

        if for_update:
            statement = statement.with_for_update()
        return self.session.scalar(statement)

    def mark_running(self, operation: Operation) -> None:
        operation.status = OperationStatus.RUNNING.value
        operation.attempt += 1
        operation.started_at = datetime.now(timezone.utc)
        operation.heartbeat_at = operation.started_at
        operation.pause_requested_at = None
        operation.cancel_requested_at = None
        operation.error_code = None
        operation.error_detail = None

    def touch_heartbeat(self, operation: Operation) -> None:
        operation.heartbeat_at = datetime.now(timezone.utc)

    def request_pause(self, operation: Operation) -> None:
        now = datetime.now(timezone.utc)
        if operation.status == OperationStatus.QUEUED.value:
            operation.status = OperationStatus.PAUSED.value
        else:
            operation.status = OperationStatus.PAUSE_REQUESTED.value
        operation.pause_requested_at = now
        operation.heartbeat_at = now

    def mark_paused(
        self,
        operation: Operation,
        *,
        reason: str | None = None,
    ) -> None:
        operation.status = OperationStatus.PAUSED.value
        operation.heartbeat_at = datetime.now(timezone.utc)
        operation.error_code = (
            "server_restarted"
            if reason == "server_restarted"
            else "checkpoint_retry" if reason else None
        )
        operation.error_detail = reason
        operation.finished_at = None

    def mark_queued_for_resume(self, operation: Operation) -> None:
        operation.status = OperationStatus.QUEUED.value
        operation.pause_requested_at = None
        operation.cancel_requested_at = None
        operation.finished_at = None

    def request_cancel(self, operation: Operation) -> None:
        now = datetime.now(timezone.utc)
        if operation.status in {
            OperationStatus.QUEUED.value,
            OperationStatus.PAUSED.value,
        }:
            self.mark_cancelled(operation)
            return
        operation.status = OperationStatus.CANCEL_REQUESTED.value
        operation.cancel_requested_at = now
        operation.heartbeat_at = now

    def mark_cancelled(
        self,
        operation: Operation,
        *,
        result: dict[str, Any] | None = None,
    ) -> None:
        operation.status = OperationStatus.CANCELLED.value
        if result is not None:
            operation.result_json = result
        operation.finished_at = datetime.now(timezone.utc)
        operation.heartbeat_at = operation.finished_at
        operation.error_code = None
        operation.error_detail = None

    def pause_orphaned_active_runs(self) -> int:
        now = datetime.now(timezone.utc)
        statement = (
            update(Operation)
            .where(
                Operation.status.in_(
                    {
                        OperationStatus.RUNNING.value,
                        OperationStatus.PAUSE_REQUESTED.value,
                    }
                )
            )
            .values(
                status=OperationStatus.PAUSED.value,
                heartbeat_at=now,
                pause_requested_at=now,
                error_code="server_restarted",
                error_detail=(
                    "The API stopped before this run completed. "
                    "Resume it from its latest LangGraph checkpoint."
                ),
            )
        )
        result = self.session.execute(statement)
        cancelled = self.session.execute(
            update(Operation)
            .where(
                Operation.status
                == OperationStatus.CANCEL_REQUESTED.value
            )
            .values(
                status=OperationStatus.CANCELLED.value,
                heartbeat_at=now,
                finished_at=now,
                error_code=None,
                error_detail=None,
            )
        )
        return int(result.rowcount or 0) + int(cancelled.rowcount or 0)

    def mark_succeeded(
        self,
        operation: Operation,
        *,
        result: dict[str, Any],
    ) -> None:
        operation.status = OperationStatus.SUCCEEDED.value
        operation.result_json = result
        operation.finished_at = datetime.now(timezone.utc)
        operation.heartbeat_at = operation.finished_at
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
        operation.heartbeat_at = datetime.now(timezone.utc)
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
        operation.heartbeat_at = operation.finished_at
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
        operation.heartbeat_at = operation.finished_at
