from __future__ import annotations

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from app.tender_agent.context import TenderRuntimeContext
from app.tender_agent.nodes.amendments import amendments_node
from app.tender_agent.nodes.base_tender import base_tender_node
from app.tender_agent.nodes.classification import (
    classification_node,
)
from app.tender_agent.nodes.evidence_validation import (
    evidence_validation_node,
)
from app.tender_agent.nodes.requirement_matrix import (
    requirement_matrix_node,
)

from app.tender_agent.nodes.coverage_audit import (
    coverage_audit_node,
)
from app.tender_agent.nodes.final_validation import (
    final_validation_node,
)
from app.tender_agent.nodes.persistence import (
    persistence_node,
)
from app.tender_agent.nodes.review_handoff import review_handoff_node
from app.tender_agent.nodes.profile_projection import (
    profile_projection_node,
)
from app.tender_agent.nodes.field_understanding import (
    field_understanding_node,
)
from app.tender_agent.nodes.inventory import inventory_node
from app.tender_agent.nodes.load_context import load_context_node
from app.tender_agent.nodes.native_extraction import (
    native_extraction_node,
)
from app.tender_agent.nodes.ocr_recovery import ocr_recovery_node
from app.tender_agent.nodes.preflight import (
    mark_failed_node,
    mark_ready_node,
    preflight_node,
)
from app.tender_agent.nodes.quality_assessment import (
    quality_assessment_node,
)
from app.tender_agent.nodes.normalization import (
    normalization_node,
)
from app.tender_agent.nodes.reconciliation import (
    reconciliation_node,
)
from app.tender_agent.nodes.retrieval import retrieval_node
from app.tender_agent.nodes.structure import structure_node
from app.tender_agent.routing import (
    route_after_amendments,
    route_after_base_tender,
    route_after_classification,
    route_after_field_understanding,
    route_after_inventory,
    route_after_load_context,
    route_after_native_extraction,
    route_after_ocr_recovery,
    route_after_preflight,
    route_after_quality_assessment,
    route_after_retrieval,
    route_after_structure,
    route_after_normalization,
    route_after_reconciliation,
    route_after_evidence_validation,
    route_after_requirement_matrix,
    route_after_coverage_audit,
    route_after_final_validation,
    route_after_persistence,
    route_after_profile_projection,
)
from app.tender_agent.state import TenderAgentState


def build_tender_graph(
    *,
    checkpointer: BaseCheckpointSaver,
):
    builder = StateGraph(
        state_schema=TenderAgentState,
        context_schema=TenderRuntimeContext,
    )

    builder.add_node("load_context", load_context_node)
    builder.add_node("inventory", inventory_node)
    builder.add_node("preflight", preflight_node)
    builder.add_node("native_extraction", native_extraction_node)
    builder.add_node(
        "quality_assessment",
        quality_assessment_node,
    )
    builder.add_node("ocr_recovery", ocr_recovery_node)
    builder.add_node("classification", classification_node)
    builder.add_node("structure", structure_node)
    builder.add_node("base_tender", base_tender_node)
    builder.add_node("amendments", amendments_node)
    builder.add_node("retrieval", retrieval_node)
    builder.add_node(
        "field_understanding",
        field_understanding_node,
    )
    builder.add_node("mark_ready", mark_ready_node)
    builder.add_node("mark_failed", mark_failed_node)

    builder.add_node(
        "requirement_matrix",
        requirement_matrix_node,
    )
    builder.add_node(
        "evidence_validation",
        evidence_validation_node,
    )
    builder.add_node(
        "profile_projection",
        profile_projection_node,
    )
    builder.add_node(
        "coverage_audit",
        coverage_audit_node,
    )
    builder.add_node(
        "final_validation",
        final_validation_node,
    )
    builder.add_node(
        "persistence",
        persistence_node,
    )
    builder.add_node("review_handoff", review_handoff_node)


    builder.add_node(
        "normalization",
        normalization_node,
    )

    builder.add_node(
        "reconciliation",
        reconciliation_node,
    )

    builder.add_edge(START, "load_context")

    builder.add_conditional_edges(
        "load_context",
        route_after_load_context,
        {"inventory": "inventory", "mark_failed": "mark_failed"},
    )
    builder.add_conditional_edges(
        "inventory",
        route_after_inventory,
        {"preflight": "preflight", "mark_failed": "mark_failed"},
    )
    builder.add_conditional_edges(
        "preflight",
        route_after_preflight,
        {
            "native_extraction": "native_extraction",
            "mark_failed": "mark_failed",
        },
    )
    builder.add_conditional_edges(
        "native_extraction",
        route_after_native_extraction,
        {
            "quality_assessment": "quality_assessment",
            "mark_failed": "mark_failed",
        },
    )
    builder.add_conditional_edges(
        "quality_assessment",
        route_after_quality_assessment,
        {
            "ocr_recovery": "ocr_recovery",
            "classification": "classification",
            "mark_failed": "mark_failed",
        },
    )
    builder.add_conditional_edges(
        "ocr_recovery",
        route_after_ocr_recovery,
        {
            "classification": "classification",
            "mark_failed": "mark_failed",
        },
    )
    builder.add_conditional_edges(
        "classification",
        route_after_classification,
        {"structure": "structure", "mark_failed": "mark_failed"},
    )
    builder.add_conditional_edges(
        "structure",
        route_after_structure,
        {
            "base_tender": "base_tender",
            "mark_failed": "mark_failed",
        },
    )
    builder.add_conditional_edges(
        "base_tender",
        route_after_base_tender,
        {"amendments": "amendments", "mark_failed": "mark_failed"},
    )
    builder.add_conditional_edges(
        "amendments",
        route_after_amendments,
        {"retrieval": "retrieval", "mark_failed": "mark_failed"},
    )
    builder.add_conditional_edges(
        "retrieval",
        route_after_retrieval,
        {
            "field_understanding": "field_understanding",
            "mark_failed": "mark_failed",
        },
    )
    builder.add_conditional_edges(
        "field_understanding",
        route_after_field_understanding,
        {
            "normalization": "normalization",
            "mark_failed": "mark_failed",
        },
    )

    builder.add_conditional_edges(
        "normalization",
        route_after_normalization,
        {
            "reconciliation": "reconciliation",
            "mark_failed": "mark_failed",
        },
    )

    builder.add_conditional_edges(
        "reconciliation",
        route_after_reconciliation,
        {
            "requirement_matrix": "requirement_matrix",
            "mark_failed": "mark_failed",
        },
    )

    builder.add_conditional_edges(
        "requirement_matrix",
        route_after_requirement_matrix,
        {
            "evidence_validation": "evidence_validation",
            "mark_failed": "mark_failed",
        },
    )

    builder.add_conditional_edges(
        "evidence_validation",
        route_after_evidence_validation,
        {
            "profile_projection": "profile_projection",
            "mark_failed": "mark_failed",
        },
    )

    builder.add_conditional_edges(
        "profile_projection",
        route_after_profile_projection,
        {
            "coverage_audit": "coverage_audit",
            "mark_failed": "mark_failed",
        },
    )

    builder.add_conditional_edges(
        "coverage_audit",
        route_after_coverage_audit,
        {
            "final_validation": "final_validation",
            "mark_failed": "mark_failed",
        },
    )

    builder.add_conditional_edges(
        "final_validation",
        route_after_final_validation,
        {
            "persistence": "persistence",
            "mark_failed": "mark_failed",
        },
    )

    builder.add_conditional_edges(
        "persistence",
        route_after_persistence,
        {
            "review_handoff": "review_handoff",
            "mark_failed": "mark_failed",
        },
    )

    builder.add_edge("review_handoff", END)
    builder.add_edge("mark_ready", END)
    builder.add_edge("mark_failed", END)

    return builder.compile(
        checkpointer=checkpointer,
        name="tender_agent",
    )
