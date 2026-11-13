export const phases = [
  { id: "context", label: "Context & inventory", color: "#38bdf8" },
  { id: "ingestion", label: "Extraction & OCR", color: "#a78bfa" },
  { id: "structure", label: "Document structure", color: "#2dd4bf" },
  { id: "understanding", label: "AI understanding", color: "#f59e0b" },
  { id: "requirements", label: "Requirements", color: "#fb7185" },
  { id: "finalization", label: "Validation & handoff", color: "#84cc16" },
];

export const workflowNodes = [
  { id: "load_context", phase: "context", label: "Load context", summary: "Loads the tender version, documents and tenant ownership.", completion: "ingestion_verified", metrics: ["ingested_document_count", "ingested_total_bytes"] },
  { id: "inventory", phase: "context", label: "Inventory", summary: "Builds the document inventory used by the graph.", completion: "ingestion_verified", metrics: ["document_ids", "ingested_document_count"] },
  { id: "preflight", phase: "context", label: "Preflight", summary: "Validates IDs, documents, ingestion and non-empty content.", metrics: ["errors", "warnings"] },
  { id: "native_extraction", phase: "ingestion", label: "Native extraction", summary: "Parses PDF, DOCX, XLSX and text without OCR where possible.", completion: "native_extraction_completed", metrics: ["document_ids", "quality_page_count"] },
  { id: "quality_assessment", phase: "ingestion", label: "Quality assessment", summary: "Scores extracted pages and decides whether OCR is necessary.", completion: "quality_assessment_completed", metrics: ["quality_page_count", "quality_passed_page_ids", "ocr_required_page_ids"] },
  { id: "ocr_recovery", phase: "ingestion", label: "OCR recovery", summary: "Processes weak or scanned pages and records provider outcomes.", completion: "ocr_recovery_completed", optional: true, metrics: ["ocr_provider_name", "ocr_succeeded_page_ids", "ocr_failed_page_ids"] },
  { id: "classification", phase: "structure", label: "Classification", summary: "Classifies tender documents and pages by semantic role.", completion: "classification_completed", metrics: ["classified_page_count", "document_type_counts", "classification_review_page_ids"] },
  { id: "structure", phase: "structure", label: "Document structure", summary: "Groups pages into logical base tender, annexure, form and amendment documents.", completion: "structure_completed", metrics: ["logical_document_count", "structured_page_count", "logical_document_type_counts"] },
  { id: "base_tender", phase: "structure", label: "Base selection", summary: "Selects the authoritative base tender and supporting documents.", completion: "base_selection_completed", metrics: ["primary_base_logical_document_id", "base_selection_confidence", "base_selection_needs_review"] },
  { id: "amendments", phase: "structure", label: "Amendments", summary: "Orders corrigenda and builds the effective source plan.", completion: "amendment_resolution_completed", metrics: ["effective_source_count", "binding_amendment_logical_document_ids", "effective_source_needs_review"] },
  { id: "retrieval", phase: "understanding", label: "Retrieval index", summary: "Chunks source pages, creates embeddings and prepares reranking.", completion: "retrieval_index_completed", metrics: ["retrieval_chunk_count", "retrieval_indexed_page_count", "retrieval_embedding_model", "retrieval_reranker_model"] },
  { id: "field_understanding", phase: "understanding", label: "Field understanding", summary: "Extracts configured tender fields with LLM evidence.", completion: "field_understanding_completed", metrics: ["configured_field_count", "found_field_count", "ambiguous_field_count", "field_review_keys"] },
  { id: "normalization", phase: "understanding", label: "Normalization", summary: "Standardizes dates, money, percentages, lists and identifiers.", completion: "normalization_completed", metrics: ["normalized_field_count", "unavailable_field_count", "normalization_error_count"] },
  { id: "reconciliation", phase: "understanding", label: "Reconciliation", summary: "Resolves candidate conflicts using source authority and amendments.", completion: "reconciliation_completed", metrics: ["reconciled_field_count", "conflict_field_count", "unresolved_field_count"] },
  { id: "requirement_matrix", phase: "requirements", label: "Requirement matrix", summary: "Extracts eligibility, technical, submission and evaluation requirements.", completion: "requirement_extraction_completed", metrics: ["requirement_count", "mandatory_requirement_count", "conditional_requirement_count"] },
  { id: "evidence_validation", phase: "requirements", label: "Evidence validation", summary: "Checks page evidence and marks valid, review or invalid requirements.", completion: "requirement_evidence_validated", metrics: ["validated_requirement_count", "review_requirement_count", "invalid_requirement_count"] },
  { id: "profile_projection", phase: "finalization", label: "Profile projection", summary: "Combines reconciled fields and requirements into one tender profile.", completion: "profile_projection_completed", metrics: ["projected_field_count", "projected_requirement_count"] },
  { id: "coverage_audit", phase: "finalization", label: "Coverage audit", summary: "Calculates readiness and identifies missing or weak coverage.", completion: "coverage_audit_completed", metrics: ["readiness_score", "coverage_issue_count", "coverage_error_count", "coverage_fatal_count"] },
  { id: "final_validation", phase: "finalization", label: "Final validation", summary: "Makes the final ready-for-review decision.", completion: "final_validation_completed", metrics: ["final_validation_status", "ready_for_review", "review_reasons"] },
  { id: "persistence", phase: "finalization", label: "Persistence", summary: "Writes the immutable Phase 15 finalization snapshot.", completion: "final_persistence_completed", metrics: ["finalization_run_id"] },
  { id: "review_handoff", phase: "finalization", label: "Review interrupt", summary: "Creates the review package, pauses LangGraph, then resumes with the human decision.", completion: "review_handoff_completed", interrupt: true, metrics: ["review_session_id", "review_status", "review_decision", "review_correction_count"] },
];

const edge = (source, target, condition, conditional = false) => ({ source, target, condition, conditional });
export const workflowEdges = [
  edge("load_context", "inventory", "context loaded"), edge("inventory", "preflight", "inventory available"),
  edge("preflight", "native_extraction", "preflight valid"), edge("native_extraction", "quality_assessment", "native extraction completed"),
  edge("quality_assessment", "ocr_recovery", "OCR page list is not empty", true), edge("quality_assessment", "classification", "no OCR required", true),
  edge("ocr_recovery", "classification", "OCR recovery completed"), edge("classification", "structure", "classification completed"),
  edge("structure", "base_tender", "structure completed"), edge("base_tender", "amendments", "base selected"),
  edge("amendments", "retrieval", "effective sources resolved"), edge("retrieval", "field_understanding", "retrieval index completed"),
  edge("field_understanding", "normalization", "fields understood"), edge("normalization", "reconciliation", "normalization completed"),
  edge("reconciliation", "requirement_matrix", "reconciliation completed"), edge("requirement_matrix", "evidence_validation", "requirements extracted"),
  edge("evidence_validation", "profile_projection", "evidence validated"), edge("profile_projection", "coverage_audit", "profile projected"),
  edge("coverage_audit", "final_validation", "coverage audited"), edge("final_validation", "persistence", "validation completed"),
  edge("persistence", "review_handoff", "persisted AND ready_for_review", true),
];

export const modeCards = [
  { key: "Native", description: "Direct parsing for digital documents", state: (s) => s?.native_extraction_completed ? "complete" : "idle" },
  { key: "OCR", description: "Recovery path only for weak pages", state: (s) => s?.ocr_required_page_ids?.length ? (s.ocr_recovery_completed ? "complete" : "active") : "skipped" },
  { key: "AI", description: "Embedding, reranking and LLM extraction", state: (s) => s?.retrieval_index_completed ? (s.field_understanding_completed ? "complete" : "active") : "idle" },
  { key: "Human", description: "LangGraph interrupt and review resume", state: (s) => s?.operation_status === "awaiting_review" ? "active" : s?.review_handoff_completed ? "complete" : "idle" },
];

export const getNodeStatus = (node, run) => {
  if (!run) return "idle";
  if (run.workflow_status === "failed" && run.current_node === node.id) return "failed";
  if (run.next_nodes?.includes(node.id)) return "waiting";
  if (run.current_node === node.id) return "running";
  if (node.completion && run[node.completion]) return "complete";
  if (["preflight", "inventory", "load_context"].includes(node.id) && run.native_extraction_completed) return "complete";
  if (node.optional && run.quality_assessment_completed && !run.ocr_required_page_ids?.length) return "skipped";
  return "idle";
};
