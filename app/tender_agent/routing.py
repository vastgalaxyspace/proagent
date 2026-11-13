from __future__ import annotations

from typing import Literal

from app.tender_agent.state import TenderAgentState


LoadContextRoute = Literal["inventory", "mark_failed"]
InventoryRoute = Literal["preflight", "mark_failed"]
PreflightRoute = Literal[
    "native_extraction",
    "mark_failed",
]
NativeExtractionRoute = Literal[
    "quality_assessment",
    "mark_failed",
]
QualityRoute = Literal[
    "ocr_recovery",
    "classification",
    "mark_failed",
]
OCRRoute = Literal["classification", "mark_failed"]
ClassificationRoute = Literal[
    "structure",
    "mark_failed",
]
StructureRoute = Literal["base_tender", "mark_failed"]
BaseTenderRoute = Literal["amendments", "mark_failed"]
AmendmentRoute = Literal["retrieval", "mark_failed"]
RetrievalRoute = Literal[
    "field_understanding",
    "mark_failed",
]
FieldUnderstandingRoute = Literal[
    "normalization",
    "mark_failed",
]

NormalizationRoute = Literal[
    "reconciliation",
    "mark_failed",
]

ReconciliationRoute = Literal[
    "requirement_matrix",
    "mark_failed",
]

RequirementMatrixRoute = Literal[
    "evidence_validation",
    "mark_failed",
]

EvidenceValidationRoute = Literal[
    "profile_projection",
    "mark_failed",
]
ProfileProjectionRoute = Literal[
    "coverage_audit",
    "mark_failed",
]

CoverageAuditRoute = Literal[
    "final_validation",
    "mark_failed",
]

FinalValidationRoute = Literal[
    "persistence",
    "mark_failed",
]

PersistenceRoute = Literal[
    "review_handoff",
    "mark_failed",
]


def route_after_load_context(
    state: TenderAgentState,
) -> LoadContextRoute:
    return (
        "mark_failed"
        if state.get("workflow_status") == "failed"
        else "inventory"
    )


def route_after_inventory(
    state: TenderAgentState,
) -> InventoryRoute:
    return (
        "mark_failed"
        if state.get("workflow_status") == "failed"
        else "preflight"
    )


def route_after_preflight(
    state: TenderAgentState,
) -> PreflightRoute:
    return (
        "mark_failed"
        if state.get("workflow_status") == "failed"
        else "native_extraction"
    )


def route_after_native_extraction(
    state: TenderAgentState,
) -> NativeExtractionRoute:
    return (
        "quality_assessment"
        if state.get("native_extraction_completed")
        else "mark_failed"
    )


def route_after_quality_assessment(
    state: TenderAgentState,
) -> QualityRoute:
    if not state.get("quality_assessment_completed", False):
        return "mark_failed"

    if state.get("ocr_required_page_ids", []):
        return "ocr_recovery"

    return "classification"


def route_after_ocr_recovery(
    state: TenderAgentState,
) -> OCRRoute:
    return (
        "classification"
        if state.get("ocr_recovery_completed")
        else "mark_failed"
    )


def route_after_classification(
    state: TenderAgentState,
) -> ClassificationRoute:
    return (
        "structure"
        if state.get("classification_completed")
        else "mark_failed"
    )


def route_after_structure(
    state: TenderAgentState,
) -> StructureRoute:
    return (
        "base_tender"
        if state.get("structure_completed")
        else "mark_failed"
    )


def route_after_base_tender(
    state: TenderAgentState,
) -> BaseTenderRoute:
    return (
        "amendments"
        if state.get("base_selection_completed")
        else "mark_failed"
    )


def route_after_amendments(
    state: TenderAgentState,
) -> AmendmentRoute:
    return (
        "retrieval"
        if state.get("amendment_resolution_completed")
        else "mark_failed"
    )


def route_after_retrieval(
    state: TenderAgentState,
) -> RetrievalRoute:
    return (
        "field_understanding"
        if state.get("retrieval_index_completed")
        else "mark_failed"
    )


def route_after_field_understanding(
    state: TenderAgentState,
) -> FieldUnderstandingRoute:
    return (
        "normalization"
        if state.get(
            "field_understanding_completed"
        )
        else "mark_failed"
    )

def route_after_normalization(
    state: TenderAgentState,
) -> NormalizationRoute:
    return (
        "reconciliation"
        if state.get("normalization_completed")
        else "mark_failed"
    )


def route_after_reconciliation(
    state: TenderAgentState,
) -> ReconciliationRoute:
    return (
        "requirement_matrix"
        if state.get("reconciliation_completed")
        else "mark_failed"
    )

def route_after_requirement_matrix(
    state: TenderAgentState,
) -> RequirementMatrixRoute:
    return (
        "evidence_validation"
        if state.get(
            "requirement_extraction_completed"
        )
        else "mark_failed"
    )


def route_after_evidence_validation(
    state: TenderAgentState,
) -> EvidenceValidationRoute:
    return (
        "profile_projection"
        if state.get(
            "requirement_evidence_validated"
        )
        else "mark_failed"
    )
def route_after_profile_projection(
    state: TenderAgentState,
) -> ProfileProjectionRoute:
    return (
        "coverage_audit"
        if state.get(
            "profile_projection_completed"
        )
        else "mark_failed"
    )


def route_after_coverage_audit(
    state: TenderAgentState,
) -> CoverageAuditRoute:
    return (
        "final_validation"
        if state.get("coverage_audit_completed")
        else "mark_failed"
    )


def route_after_final_validation(
    state: TenderAgentState,
) -> FinalValidationRoute:
    if not state.get(
        "final_validation_completed"
    ):
        return "mark_failed"

    return "persistence"


def route_after_persistence(
    state: TenderAgentState,
) -> PersistenceRoute:
    if not state.get("final_persistence_completed"):
        return "mark_failed"

    return (
        "review_handoff"
        if state.get("ready_for_review")
        else "mark_failed"
    )


