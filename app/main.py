from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Request
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.tender_agent.services.amendment_service import (
    AmendmentService,
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
from app.tender_agent.services.normalization_service import (
    NormalizationService,
)
from app.tender_agent.services.reconciliation_service import (
    ReconciliationService,
)
from app.tender_agent.services.retrieval_service import (
    RetrievalLimits,
    RetrievalService,
)
from app.tender_agent.services.base_tender_service import (
    BaseTenderService,
)
from app.tender_agent.services.structure_service import (
    StructureService,
)
from app.tender_agent.services.field_catalog_service import (
    FieldCatalogService,
)
from app.tender_agent.services.understanding_service import (
    UnderstandingService,
)

from app.api.dependencies import get_database_session
from app.api.tender_routes import router as tender_router
from app.core.config import get_settings
from app.infrastructure.checkpointing.langgraph_postgres import (
    postgres_checkpointer,
)
from app.infrastructure.database.session import create_database
from app.infrastructure.providers.ocr import build_ocr_provider
from app.infrastructure.providers.registry import (
    build_ai_provider_registry,
)
from app.infrastructure.providers.settings import (
    get_openparser_settings,
)
from app.infrastructure.storage.local_storage import LocalObjectStorage
from app.tender_agent.graph import build_tender_graph
from app.tender_agent.handoff import HandoffService
from app.tender_agent.schemas.responses import (
    HealthResponse,
    ReadinessResponse,
)
from app.tender_agent.services.classification_service import (
    ClassificationLimits,
    TenderClassificationService,
)
from app.tender_agent.services.native_parser import (
    NativeDocumentParser,
    NativeParserLimits,
)
from app.tender_agent.services.quality_service import (
    QualityLimits,
    QualityService,
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    ai_providers = (
        build_ai_provider_registry()
        if settings.ai_enabled
        else None
    )
    retrieval_service = (
        RetrievalService(
            embedding_provider=(
                ai_providers.embeddings
            ),
            reranker_provider=(
                ai_providers.reranker
            ),
            limits=RetrievalLimits(
                chunk_characters=(
                    settings
                    .retrieval_chunk_characters
                ),
                chunk_overlap_characters=(
                    settings
                    .retrieval_chunk_overlap_characters
                ),
                search_candidate_pool=(
                    settings
                    .retrieval_search_candidate_pool
                ),
            ),
        )
        if ai_providers is not None
        else None
    )
    field_catalog = FieldCatalogService(
        config_path=settings.tender_fields_config_path,
    ).load()

    normalization_service = NormalizationService(
        default_currency=(
            settings.normalization_default_currency
        ),
        default_timezone=(
            settings.normalization_default_timezone
        ),
    )

    reconciliation_service = ReconciliationService(
        minimum_confidence=(
            settings.reconciliation_minimum_confidence
        )
    )

    understanding_service = (
        UnderstandingService(
            llm=ai_providers.llm,
            retrieval_service=retrieval_service,
            prompt_path=(
                settings.field_understanding_prompt_path
            ),
            retrieval_limit=(
                settings.field_retrieval_limit
            ),
            minimum_confidence=(
                settings.field_minimum_confidence
            ),
            max_chunk_characters=(
                settings.field_max_chunk_characters
            ),
        )
        if ai_providers is not None
        and retrieval_service is not None
        else None
    )

    requirement_service = (
        RequirementService(
            llm=ai_providers.llm,
            retrieval_service=retrieval_service,
            catalog_path=(
                settings.requirement_dictionary_path
            ),
            prompt_path=(
                settings.requirement_prompt_path
            ),
            retrieval_limit=(
                settings.requirement_retrieval_limit
            ),
            minimum_confidence=(
                settings
                .requirement_minimum_confidence
            ),
            max_chunk_characters=(
                settings
                .requirement_max_chunk_characters
            ),
        )
        if ai_providers is not None
        and retrieval_service is not None
        else None
    )

    evidence_service = EvidenceService()
    coverage_service = CoverageService(
        policy_path=settings.coverage_policy_path,
    )
    validation_service = ValidationService()
    handoff_service = HandoffService()
    database = create_database(settings.database_url)
    object_storage = LocalObjectStorage(settings.storage_root)
    native_parser = NativeDocumentParser(
        NativeParserLimits(
            max_pdf_pages=settings.max_pdf_pages,
            max_document_characters=(
                settings.max_document_characters
            ),
            min_native_page_characters=(
                settings.min_native_page_characters
            ),
            max_archive_files=settings.max_archive_files,
            max_archive_total_bytes=(
                settings.max_archive_total_bytes
            ),
            max_archive_entry_bytes=(
                settings.max_archive_entry_bytes
            ),
            max_archive_compression_ratio=(
                settings.max_archive_compression_ratio
            ),
            max_spreadsheet_cells=(
                settings.max_spreadsheet_cells
            ),
            office_converter_bin=settings.office_converter_bin,
            office_converter_timeout_seconds=(
                settings.office_converter_timeout_seconds
            ),
        )
    )

    classification_service = TenderClassificationService(
        ClassificationLimits(
            probe_characters=(
                settings.classification_probe_characters
            ),
            minimum_confidence=(
                settings.classification_minimum_confidence
            ),
        )
    )
    structure_service = StructureService(
        minimum_confidence=(
            settings.classification_minimum_confidence
        )
    )
    base_tender_service = BaseTenderService()
    amendment_service = AmendmentService(
        llm=(
            ai_providers.llm
            if ai_providers is not None
            else None
        ),
        field_catalog=field_catalog,
        minimum_confidence=(
            settings.amendment_minimum_confidence
        ),
        max_source_characters=(
            settings.amendment_max_source_characters
        ),
    )
    quality_service = QualityService(
        QualityLimits(
            min_characters=settings.ocr_min_page_characters,
            min_words=settings.ocr_min_words,
            min_alphanumeric_characters=(
                settings.ocr_min_alphanumeric_characters
            ),
            max_noise_ratio=settings.ocr_max_noise_ratio,
            long_token_characters=(
                settings.native_text_long_token_characters
            ),
            long_token_ratio=(
                settings.native_text_long_token_ratio
            ),
            repeated_boilerplate_min_pages=(
                settings.repeated_boilerplate_min_pages
            ),
            repeated_boilerplate_min_line_characters=(
                settings
                .repeated_boilerplate_min_line_characters
            ),
            max_ocr_characters=(
                settings.max_document_characters
            ),
        )
    )
    ocr_provider = build_ocr_provider(
        enabled=settings.ocr_enabled,
        provider_name=settings.ocr_provider,
        tesseract_command=settings.tesseract_command,
        language=settings.ocr_language,
        render_scale=settings.ocr_render_scale,
        timeout_seconds=settings.ocr_timeout_seconds,
        openparser_settings=(
            get_openparser_settings()
            if settings.ocr_enabled
            and settings.ocr_provider == "openparser"
            else None
        ),
    )

    with postgres_checkpointer(
        database_url=settings.database_url,
        min_pool_size=settings.checkpoint_pool_min_size,
        max_pool_size=settings.checkpoint_pool_max_size,
    ) as checkpointer:
        app.state.database = database
        app.state.object_storage = object_storage
        app.state.native_parser = native_parser
        app.state.quality_service = quality_service
        app.state.ocr_provider = ocr_provider
        app.state.ai_providers = ai_providers
        app.state.classification_service = (
            classification_service
        )
        app.state.retrieval_service = (
            retrieval_service
        )
        app.state.field_catalog = field_catalog
        app.state.understanding_service = (
            understanding_service
        )
        app.state.normalization_service = (
            normalization_service
        )
        app.state.reconciliation_service = (
            reconciliation_service
        )
        app.state.requirement_service = (
            requirement_service
        )
        app.state.evidence_service = evidence_service
        app.state.coverage_service = coverage_service
        app.state.validation_service = validation_service
        app.state.handoff_service = handoff_service
        app.state.structure_service = structure_service
        app.state.base_tender_service = base_tender_service
        app.state.amendment_service = amendment_service
        app.state.tender_checkpointer = checkpointer
        app.state.tender_graph = build_tender_graph(
            checkpointer=checkpointer,
        )

        try:
            yield
        finally:
            app.state.tender_graph = None
            app.state.tender_checkpointer = None
            app.state.native_parser = None
            app.state.quality_service = None
            app.state.ocr_provider = None
            app.state.ai_providers = None
            app.state.classification_service = None
            app.state.object_storage = None
            app.state.database = None
            app.state.structure_service = None
            app.state.base_tender_service = None
            app.state.amendment_service = None
            app.state.retrieval_service = None
            app.state.field_catalog = None
            app.state.understanding_service = None
            app.state.normalization_service = None
            app.state.reconciliation_service = None
            app.state.requirement_service = None
            app.state.evidence_service = None
            app.state.coverage_service = None
            app.state.validation_service = None
            app.state.handoff_service = None

    database.dispose()


settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    debug=settings.debug,
    lifespan=lifespan,
)


@app.get(
    "/health",
    response_model=HealthResponse,
    tags=["system"],
)
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        application=settings.app_name,
        environment=settings.app_environment,
    )


@app.get(
    "/ready",
    response_model=ReadinessResponse,
    tags=["system"],
)
def readiness(
    request: Request,
    session: Annotated[
        Session,
        Depends(get_database_session),
    ],
) -> ReadinessResponse:
    session.execute(text("SELECT 1"))

    return ReadinessResponse(
        status="ready",
        database="connected",
        checkpoint_store="connected",
        object_storage="available",
        ocr_provider=request.app.state.ocr_provider.name,
        ocr_available=(
            request.app.state.ocr_provider.is_available()
        ),
        ocr_model=getattr(
            request.app.state.ocr_provider,
            "model",
            None,
        ),
        ai_enabled=settings.ai_enabled,
        ai_provider=(
            request.app.state.ai_providers.settings.provider
            if request.app.state.ai_providers
            else None
        ),
        main_llm_model=(
            request.app.state.ai_providers.llm.model
            if request.app.state.ai_providers
            else None
        ),
        verifier_model=(
            request.app.state.ai_providers.verifier.model
            if request.app.state.ai_providers
            else None
        ),
        embedding_model=(
            request.app.state.ai_providers.embeddings.model
            if request.app.state.ai_providers
            else None
        ),
        reranker_model=(
            request.app.state.ai_providers.reranker.model
            if request.app.state.ai_providers
            else None
        ),
    )


app.include_router(
    tender_router,
    prefix=settings.api_prefix,
)
