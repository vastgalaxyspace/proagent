from __future__ import annotations

from app.tender_agent.state import TenderAgentState


def preflight_node(state: TenderAgentState) -> TenderAgentState:
    errors: list[str] = []



    if not state.get("request_id", "").strip():
        errors.append("Request ID is required.")

    if not state.get("tender_id", "").strip():
        errors.append("Tender ID is required.")

    if not state.get("tender_version_id", "").strip():
        errors.append("Tender version ID is required.")

    if not state.get("operation_id", "").strip():
        errors.append("Operation ID is required.")

    if not state.get("document_ids", []):
        errors.append("At least one tender document is required.")
    
    if not state.get("ingestion_verified", False):
        errors.append("Tender document ingestion was not verified.")
    
    if state.get("ingested_document_count", 0) <= 0:
        errors.append("No ingested tender documents were found.")
    
    if state.get("ingested_total_bytes", 0) <= 0:
        errors.append("The ingested tender documents are empty.")

    if errors:
        return {
            "workflow_status": "failed",
            "current_node": "preflight",
            "next_action": "mark_failed",
            "errors": errors,
        }

    return {
        "workflow_status": "validating",
        "current_node": "preflight",
        "next_action": "native_extraction",
    }


def mark_ready_node(state: TenderAgentState) -> TenderAgentState:
    return {
        "workflow_status": "ready",
        "current_node": "mark_ready",
        "next_action": None,
    }


def mark_failed_node(state: TenderAgentState) -> TenderAgentState:
    return {
        "workflow_status": "failed",
        "current_node": "mark_failed",
        "next_action": None,
    }
