from __future__ import annotations

from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.infrastructure.database.models import (
    Document,
    Tender,
    TenderVersion,
)
from app.tender_agent.domain.statuses import (
    DocumentExtractionStatus,
    DocumentStorageStatus,
    TenderStatus,
    TenderVersionStatus,
)


class TenderRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_tender(
        self,
        *,
        tenant_id: str,
        title: str,
        external_reference: str | None,
        document_names: list[tuple[str, str | None]],
    ) -> tuple[Tender, TenderVersion, list[Document]]:
        tender = Tender(
            tenant_id=tenant_id,
            title=title,
            external_reference=external_reference,
            status=TenderStatus.DRAFT.value,
        )

        self.session.add(tender)
        self.session.flush()

        version = TenderVersion(
            tender_id=tender.id,
            version_number=1,
            status=TenderVersionStatus.DRAFT.value,
            understanding_json={},
        )

        self.session.add(version)
        self.session.flush()

        documents = [
            Document(
                tenant_id=tenant_id,
                tender_version_id=version.id,
                file_name=file_name,
                content_type=content_type,
                storage_status=DocumentStorageStatus.PENDING.value,
                extraction_status=DocumentExtractionStatus.PENDING.value,
            )
            for file_name, content_type in document_names
        ]

        self.session.add_all(documents)
        self.session.flush()

        return tender, version, documents

    def get_tender_for_tenant(
        self,
        *,
        tender_id: UUID,
        tenant_id: str,
    ) -> Tender | None:
        statement: Select[tuple[Tender]] = select(Tender).where(
            Tender.id == tender_id,
            Tender.tenant_id == tenant_id,
        )

        return self.session.scalar(statement)

    def get_current_version(
        self,
        *,
        tender_id: UUID,
        tenant_id: str,
    ) -> TenderVersion | None:
        statement: Select[tuple[TenderVersion]] = (
            select(TenderVersion)
            .join(Tender, Tender.id == TenderVersion.tender_id)
            .where(
                Tender.id == tender_id,
                Tender.tenant_id == tenant_id,
                TenderVersion.status
                != TenderVersionStatus.SUPERSEDED.value,
            )
            .order_by(TenderVersion.version_number.desc())
            .limit(1)
        )

        return self.session.scalar(statement)

    def get_version_for_tenant(
        self,
        *,
        version_id: UUID,
        tenant_id: str,
    ) -> TenderVersion | None:
        statement: Select[tuple[TenderVersion]] = (
            select(TenderVersion)
            .join(Tender, Tender.id == TenderVersion.tender_id)
            .where(
                TenderVersion.id == version_id,
                Tender.tenant_id == tenant_id,
            )
        )

        return self.session.scalar(statement)