from __future__ import annotations

from collections.abc import Callable

from sqlalchemy.orm import Session
from typing_extensions import NotRequired, TypedDict

from app.infrastructure.providers.registry import AIProviderRegistry
from app.infrastructure.providers.ocr import OCRProvider
from app.infrastructure.storage.interface import ObjectStorage
from app.tender_agent.services.native_parser import (
    NativeDocumentParser,
)
from app.tender_agent.services.normalization_service import (
    NormalizationService,
)
from app.tender_agent.services.coverage_service import (
    CoverageService,
)
from app.tender_agent.services.validation_service import (
    ValidationService,
)
from app.tender_agent.services.evidence_service import (
    EvidenceService,
)
from app.tender_agent.services.requirement_service import (
    RequirementService,
)
from app.tender_agent.services.reconciliation_service import (
    ReconciliationService,
)
from app.tender_agent.services.retrieval_service import (
    RetrievalService,
)
from app.tender_agent.schemas.field_schema import (
    TenderFieldCatalog,
)
from app.tender_agent.services.understanding_service import (
    UnderstandingService,
)
from app.tender_agent.services.amendment_service import (
    AmendmentService,
)
from app.tender_agent.services.base_tender_service import (
    BaseTenderService,
)
from app.tender_agent.services.quality_service import (
    QualityService,
)
from app.tender_agent.services.classification_service import (
    TenderClassificationService,
)
from app.tender_agent.services.structure_service import (
    StructureService,
)
from app.tender_agent.handoff import HandoffService

class TenderRuntimeContext(TypedDict):
    tenant_id: str
    user_id: str
    session_factory: Callable[[], Session]
    object_storage: ObjectStorage
    native_parser: NativeDocumentParser
    quality_service: QualityService
    ocr_provider: OCRProvider
    retrieval_service: NotRequired[RetrievalService]
    ocr_max_attempts: int
    ocr_min_accepted_score: float
    ocr_failure_policy: str
    max_document_characters: int
    classification_service: TenderClassificationService
    structure_service: StructureService
    base_tender_service: BaseTenderService
    amendment_service: AmendmentService
    ai_providers: NotRequired[AIProviderRegistry]

    field_catalog: NotRequired[
        TenderFieldCatalog
    ]

    understanding_service: NotRequired[
        UnderstandingService
    ]
    normalization_service: NotRequired[
        NormalizationService
    ]

    reconciliation_service: NotRequired[
        ReconciliationService
    ]

    requirement_service: NotRequired[
        RequirementService
    ]
    evidence_service: NotRequired[
        EvidenceService
    ]
    coverage_service: NotRequired[
        CoverageService
    ]
    validation_service: NotRequired[
        ValidationService
    ]
    handoff_service: NotRequired[HandoffService]
    thread_id: NotRequired[str]

