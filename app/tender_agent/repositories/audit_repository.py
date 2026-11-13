from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.infrastructure.database.models import AuditEvent


class AuditRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def record(
        self,
        *,
        tenant_id: str,
        actor_user_id: str | None,
        event_type: str,
        entity_type: str,
        entity_id: str,
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
    ) -> AuditEvent:
        event = AuditEvent(
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            before_json=before,
            after_json=after,
        )

        self.session.add(event)
        self.session.flush()

        return event