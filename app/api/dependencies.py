from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Annotated, Any
from app.tender_agent.services.structure_service import (
    StructureService,
)
from app.tender_agent.services.amendment_service import (
    AmendmentService,
)
from app.tender_agent.services.coverage_service import (
    CoverageService,
)
from app.tender_agent.services.validation_service import (
    ValidationService,
)
from app.tender_agent.services.normalization_service import (
    NormalizationService,
)
from app.tender_agent.services.reconciliation_service import (
    ReconciliationService,
)
from app.tender_agent.services.evidence_service import (
    EvidenceService,
)
from app.tender_agent.services.requirement_service import (
    RequirementService,
)
from app.tender_agent.services.base_tender_service import (
    BaseTenderService,
)
from fastapi import Header, HTTPException, Request, status
from sqlalchemy.orm import Session, sessionmaker
from app.tender_agent.services.retrieval_service import (
    RetrievalService,
)
from app.tender_agent.schemas.field_schema import (
    TenderFieldCatalog,
)
from app.tender_agent.services.understanding_service import (
    UnderstandingService,
)
from app.tender_agent.services.classification_service import (
    TenderClassificationService,
)

from app.infrastructure.database.session import DatabaseRuntime
from app.infrastructure.providers.registry import AIProviderRegistry
from app.infrastructure.providers.ocr import OCRProvider
from app.infrastructure.storage.interface import ObjectStorage
from app.tender_agent.services.native_parser import (
    NativeDocumentParser,
)
from app.tender_agent.services.quality_service import QualityService
from app.tender_agent.handoff import HandoffService


@dataclass(frozen=True)
class RequestContext:
    tenant_id: str
    user_id: str


def get_ai_providers(request: Request) -> AIProviderRegistry:
    providers = getattr(
        request.app.state,
        "ai_providers",
        None,
    )

    if providers is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "AI providers are disabled or unavailable."
            ),
        )

    return providers

def get_retrieval_service(
    request: Request,
) -> RetrievalService:
    service = getattr(
        request.app.state,
        "retrieval_service",
        None,
    )

    if service is None:
        raise HTTPException(
            status_code=(
                status.HTTP_503_SERVICE_UNAVAILABLE
            ),
            detail=(
                "Retrieval service is unavailable. "
                "Enable and configure AI providers."
            ),
        )

    return service


def get_field_catalog(
    request: Request,
) -> TenderFieldCatalog:
    catalog = getattr(
        request.app.state,
        "field_catalog",
        None,
    )

    if catalog is None:
        raise HTTPException(
            status_code=(
                status.HTTP_503_SERVICE_UNAVAILABLE
            ),
            detail="Tender field catalog is unavailable.",
        )

    return catalog


def get_understanding_service(
    request: Request,
) -> UnderstandingService:
    service = getattr(
        request.app.state,
        "understanding_service",
        None,
    )

    if service is None:
        raise HTTPException(
            status_code=(
                status.HTTP_503_SERVICE_UNAVAILABLE
            ),
            detail=(
                "Field-understanding service is unavailable. "
                "Enable and configure AI providers."
            ),
        )

    return service

def get_normalization_service(
    request: Request,
) -> NormalizationService:
    service = getattr(
        request.app.state,
        "normalization_service",
        None,
    )

    if service is None:
        raise HTTPException(
            status_code=(
                status.HTTP_503_SERVICE_UNAVAILABLE
            ),
            detail="Normalization service is unavailable.",
        )

    return service


def get_reconciliation_service(
    request: Request,
) -> ReconciliationService:
    service = getattr(
        request.app.state,
        "reconciliation_service",
        None,
    )

    if service is None:
        raise HTTPException(
            status_code=(
                status.HTTP_503_SERVICE_UNAVAILABLE
            ),
            detail="Reconciliation service is unavailable.",
        )

    return service


def get_requirement_service(
    request: Request,
) -> RequirementService:
    service = getattr(
        request.app.state,
        "requirement_service",
        None,
    )

    if service is None:
        raise HTTPException(
            status_code=(
                status.HTTP_503_SERVICE_UNAVAILABLE
            ),
            detail=(
                "Requirement extraction service is "
                "unavailable."
            ),
        )

    return service


def get_evidence_service(
    request: Request,
) -> EvidenceService:
    service = getattr(
        request.app.state,
        "evidence_service",
        None,
    )

    if service is None:
        raise HTTPException(
            status_code=(
                status.HTTP_503_SERVICE_UNAVAILABLE
            ),
            detail=(
                "Evidence validation service is "
                "unavailable."
            ),
        )

    return service


def get_object_storage(request: Request) -> ObjectStorage:
    storage = getattr(request.app.state, "object_storage", None)

    if storage is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Object storage is unavailable.",
        )

    return storage


def get_classification_service(
    request: Request,
) -> TenderClassificationService:
    service = getattr(
        request.app.state,
        "classification_service",
        None,
    )

    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Tender classification service "
                "is unavailable."
            ),
        )

    return service


def get_base_tender_service(
    request: Request,
) -> BaseTenderService:
    service = getattr(
        request.app.state,
        "base_tender_service",
        None,
    )

    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Base-tender service is unavailable.",
        )

    return service


def get_amendment_service(
    request: Request,
) -> AmendmentService:
    service = getattr(
        request.app.state,
        "amendment_service",
        None,
    )

    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Amendment service is unavailable.",
        )

    return service
    
def get_native_parser(
    request: Request,
) -> NativeDocumentParser:
    parser = getattr(request.app.state, "native_parser", None)

    if parser is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Native document parser is unavailable.",
        )

    return parser

def get_structure_service(
    request: Request,
) -> StructureService:
    service = getattr(
        request.app.state,
        "structure_service",
        None,
    )

    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Tender structure service is unavailable."
            ),
        )

    return service


def get_quality_service(request: Request) -> QualityService:
    service = getattr(request.app.state, "quality_service", None)

    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Page quality service is unavailable.",
        )

    return service


def get_ocr_provider(request: Request) -> OCRProvider:
    provider = getattr(request.app.state, "ocr_provider", None)

    if provider is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OCR provider is unavailable.",
        )

    return provider


def get_request_context(
    tenant_id: Annotated[str | None, Header(alias="X-Tenant-ID")] = None,
    user_id: Annotated[str | None, Header(alias="X-User-ID")] = None,
) -> RequestContext:
    normalized_tenant_id = (tenant_id or "").strip()
    normalized_user_id = (user_id or "").strip()

    if not normalized_tenant_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-Tenant-ID header is required.",
        )

    if not normalized_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-User-ID header is required.",
        )

    return RequestContext(
        tenant_id=normalized_tenant_id,
        user_id=normalized_user_id,
    )


def get_tender_graph(request: Request) -> Any:
    graph = getattr(request.app.state, "tender_graph", None)

    if graph is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Tender Agent graph is unavailable.",
        )

    return graph


def get_database(request: Request) -> DatabaseRuntime:
    database = getattr(request.app.state, "database", None)

    if database is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is unavailable.",
        )

    return database


def get_database_session(request: Request) -> Iterator[Session]:
    database = get_database(request)
    session = database.session_factory()

    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_session_factory(
    request: Request,
) -> sessionmaker[Session]:
    return get_database(request).session_factory


def get_coverage_service(
    request: Request,
) -> CoverageService:
    service = getattr(
        request.app.state,
        "coverage_service",
        None,
    )

    if service is None:
        raise HTTPException(
            status_code=(
                status.HTTP_503_SERVICE_UNAVAILABLE
            ),
            detail="Coverage service is unavailable.",
        )

    return service


def get_validation_service(
    request: Request,
) -> ValidationService:
    service = getattr(
        request.app.state,
        "validation_service",
        None,
    )

    if service is None:
        raise HTTPException(
            status_code=(
                status.HTTP_503_SERVICE_UNAVAILABLE
            ),
            detail=(
                "Final validation service is unavailable."
            ),
        )

    return service


def get_handoff_service(request: Request) -> HandoffService:
    service = getattr(request.app.state, "handoff_service", None)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Review handoff service is unavailable.",
        )
    return service
