export const phases = [
  { id: "context", label: "Context & inventory", color: "#38bdf8" },
  { id: "ingestion", label: "Extraction & OCR", color: "#a78bfa" },
  { id: "structure", label: "Document structure", color: "#2dd4bf" },
  { id: "understanding", label: "AI understanding", color: "#f59e0b" },
  { id: "requirements", label: "Requirements", color: "#fb7185" },
  { id: "finalization", label: "Validation & handoff", color: "#84cc16" },
];

export const workflowNodes = [
  { id: "load_context", phase: "context", label: "Load context", summary: "Loads the tender version, documents and tenant ownership.", completion: "ingestion_verified", metrics: ["ingested_document_count", "ingested_total_bytes"], tasks: [
    { title: "Load tender identifiers", description: "Read the tender, version, tenant, user and LangGraph thread identifiers." },
    { title: "Load saved records", description: "Fetch the tender version and its uploaded document records from storage." },
    { title: "Initialize graph context", description: "Put the validated identifiers and document references into workflow state." },
  ] },
  { id: "inventory", phase: "context", label: "Inventory", summary: "Builds the document inventory used by the graph.", completion: "ingestion_verified", metrics: ["document_ids", "ingested_document_count"], tasks: [
    { title: "List uploaded documents", description: "Create one inventory entry for every stored upload." },
    { title: "Capture file metadata", description: "Record names, types, sizes, hashes and storage locations." },
    { title: "Verify ingestion", description: "Confirm the stored files are available before extraction begins." },
  ] },
  { id: "preflight", phase: "context", label: "Preflight", summary: "Validates IDs, documents, ingestion and non-empty content.", metrics: ["errors", "warnings"], tasks: [
    { title: "Validate workflow input", description: "Check required tender, version, tenant and document values." },
    { title: "Check document readiness", description: "Reject missing, empty or unsupported input before expensive processing." },
    { title: "Record warnings and errors", description: "Save actionable preflight findings for the run and UI." },
  ] },
  { id: "native_extraction", phase: "ingestion", label: "Native extraction", summary: "Parses PDF, DOCX, XLSX and text without OCR where possible.", completion: "native_extraction_completed", metrics: ["document_ids", "quality_page_count"], tasks: [
    { title: "Open each source independently", description: "Expand safe ZIP members and process valid files without one bad member stopping the rest." },
    { title: "Extract native content", description: "Read text, pages and tables from PDF, DOCX, XLSX and text sources." },
    { title: "Preserve provenance", description: "Keep every page linked to its source file and collect extraction warnings." },
  ] },
  { id: "quality_assessment", phase: "ingestion", label: "Quality assessment", summary: "Scores extracted pages and decides whether OCR is necessary.", completion: "quality_assessment_completed", metrics: ["quality_page_count", "quality_passed_page_ids", "ocr_required_page_ids"], tasks: [
    { title: "Measure readable text", description: "Assess text length, character quality and other page-level signals." },
    { title: "Separate good and weak pages", description: "Mark usable native pages as passed and scanned or weak pages for recovery." },
    { title: "Choose the conditional edge", description: "Route to OCR only when at least one page requires it; otherwise continue to classification." },
  ] },
  { id: "ocr_recovery", phase: "ingestion", label: "OCR recovery", summary: "Processes weak or scanned pages and records provider outcomes.", completion: "ocr_recovery_completed", optional: true, metrics: ["ocr_provider_name", "ocr_succeeded_page_ids", "ocr_failed_page_ids"], tasks: [
    { title: "Send only weak pages", description: "Submit pages selected by quality assessment to the configured OCR provider." },
    { title: "Recover text and layout", description: "Capture OCR text, tables, layout coordinates and provider metadata." },
    { title: "Apply failure policy", description: "Keep readable pages, report failed OCR pages and fail only when the configured policy requires it." },
  ] },
  { id: "classification", phase: "structure", label: "Classification", summary: "Classifies tender documents and pages by semantic role.", completion: "classification_completed", metrics: ["classified_page_count", "document_type_counts", "classification_review_page_ids"], tasks: [
    { title: "Inspect deterministic signals", description: "Use filenames, headings, page text and configured keywords." },
    { title: "Assign document roles", description: "Classify content as base tender, annexure, corrigendum, form or another supported role." },
    { title: "Flag uncertain results", description: "Record confidence and send ambiguous pages for later review." },
  ] },
  { id: "structure", phase: "structure", label: "Document structure", summary: "Groups pages into logical base tender, annexure, form and amendment documents.", completion: "structure_completed", metrics: ["logical_document_count", "structured_page_count", "logical_document_type_counts"], tasks: [
    { title: "Find document boundaries", description: "Use source changes, headings, roles, types and page continuity to detect boundaries." },
    { title: "Group related pages", description: "Build logical documents for base tenders, annexures, forms and amendments." },
    { title: "Persist page membership", description: "Save document order and the exact pages belonging to each logical document." },
  ] },
  { id: "base_tender", phase: "structure", label: "Base selection", summary: "Selects the authoritative base tender and supporting documents.", completion: "base_selection_completed", metrics: ["primary_base_logical_document_id", "base_selection_confidence", "base_selection_needs_review"], tasks: [
    { title: "Score base candidates", description: "Rank logical documents using type, title, contents and source authority." },
    { title: "Select the primary tender", description: "Choose the most authoritative base document with a confidence score." },
    { title: "Retain supporting sources", description: "Keep relevant attachments, notices and uncertain sources in the authoritative set." },
  ] },
  { id: "amendments", phase: "structure", label: "Amendments", summary: "Orders corrigenda and builds the effective source plan.", completion: "amendment_resolution_completed", metrics: ["effective_source_count", "binding_amendment_logical_document_ids", "effective_source_needs_review"], tasks: [
    { title: "Identify amendment sources", description: "Find corrigenda, addenda and pre-bid clarifications that may change the tender." },
    { title: "Order by authority and date", description: "Create the sequence in which base and amendment sources must be interpreted." },
    { title: "Build the effective source plan", description: "Mark binding sources and flag ambiguous amendment relationships for review." },
  ] },
  { id: "retrieval", phase: "understanding", label: "Retrieval index", summary: "Chunks source pages, creates embeddings and prepares reranking.", completion: "retrieval_index_completed", metrics: ["retrieval_chunk_count", "retrieval_indexed_page_count", "retrieval_embedding_model", "retrieval_reranker_model"], tasks: [
    { title: "Create evidence chunks", description: "Split authoritative pages into searchable units while preserving page references." },
    { title: "Generate embeddings", description: "Convert chunks into vectors with the configured embedding model." },
    { title: "Prepare ranked retrieval", description: "Store chunk metadata and configure semantic retrieval plus LLM reranking." },
  ] },
  { id: "field_understanding", phase: "understanding", label: "Field understanding", summary: "Extracts configured tender fields with LLM evidence.", completion: "field_understanding_completed", metrics: ["configured_field_count", "found_field_count", "ambiguous_field_count", "field_review_keys"], tasks: [
    { title: "Load configured fields", description: "Read the field definitions, including the configured 31 tender fields." },
    { title: "Retrieve field evidence", description: "Search and rerank the most relevant chunks for each field." },
    { title: "Extract grounded values", description: "Use the main LLM to return structured values, citations, confidence and ambiguity status." },
  ] },
  { id: "normalization", phase: "understanding", label: "Normalization", summary: "Standardizes dates, money, percentages, lists and identifiers.", completion: "normalization_completed", metrics: ["normalized_field_count", "unavailable_field_count", "normalization_error_count"], tasks: [
    { title: "Preserve raw values", description: "Keep the original extracted text and evidence unchanged for auditability." },
    { title: "Standardize data types", description: "Normalize dates, currency, amounts, percentages, lists and identifiers." },
    { title: "Report conversion issues", description: "Mark unavailable or invalid values without inventing replacements." },
  ] },
  { id: "reconciliation", phase: "understanding", label: "Reconciliation", summary: "Resolves candidate conflicts using source authority and amendments.", completion: "reconciliation_completed", metrics: ["reconciled_field_count", "conflict_field_count", "unresolved_field_count"], tasks: [
    { title: "Collect competing candidates", description: "Compare all normalized values and their evidence for each field." },
    { title: "Apply source precedence", description: "Prefer authoritative and later binding amendments over superseded content." },
    { title: "Resolve or flag conflicts", description: "Choose a supported result or retain the conflict for human review." },
  ] },
  { id: "requirement_matrix", phase: "requirements", label: "Requirement matrix", summary: "Extracts eligibility, technical, submission and evaluation requirements.", completion: "requirement_extraction_completed", metrics: ["requirement_count", "mandatory_requirement_count", "conditional_requirement_count"], tasks: [
    { title: "Retrieve requirement passages", description: "Find evidence describing bidder obligations and evaluation rules." },
    { title: "Extract requirement records", description: "Use the LLM to create eligibility, technical, submission, compliance and evaluation entries." },
    { title: "Label obligation strength", description: "Mark mandatory, conditional and informational requirements with evidence." },
  ] },
  { id: "evidence_validation", phase: "requirements", label: "Evidence validation", summary: "Checks page evidence and marks valid, review or invalid requirements.", completion: "requirement_evidence_validated", metrics: ["validated_requirement_count", "review_requirement_count", "invalid_requirement_count"], tasks: [
    { title: "Verify cited sources", description: "Confirm every citation points to a known document, page and chunk." },
    { title: "Check quote support", description: "Ensure the evidence text actually supports the extracted requirement." },
    { title: "Assign evidence status", description: "Mark each requirement valid, needs review or invalid." },
  ] },
  { id: "profile_projection", phase: "finalization", label: "Profile projection", summary: "Combines reconciled fields and requirements into one tender profile.", completion: "profile_projection_completed", metrics: ["projected_field_count", "projected_requirement_count"], tasks: [
    { title: "Project final fields", description: "Copy reconciled field values and their evidence into the tender profile." },
    { title: "Attach requirements", description: "Add the validated requirement matrix to the same review model." },
    { title: "Build one reviewable view", description: "Create the complete tender understanding consumed by later agents and the UI." },
  ] },
  { id: "coverage_audit", phase: "finalization", label: "Coverage audit", summary: "Calculates readiness and identifies missing or weak coverage.", completion: "coverage_audit_completed", metrics: ["readiness_score", "coverage_issue_count", "coverage_error_count", "coverage_fatal_count"], tasks: [
    { title: "Measure field coverage", description: "Check configured fields for missing, ambiguous or unsupported values." },
    { title: "Measure requirement coverage", description: "Check requirement categories and evidence completeness." },
    { title: "Calculate readiness", description: "Produce severity-based issues and an overall readiness score." },
  ] },
  { id: "final_validation", phase: "finalization", label: "Final validation", summary: "Makes the final ready-for-review decision.", completion: "final_validation_completed", metrics: ["final_validation_status", "ready_for_review", "review_reasons"], tasks: [
    { title: "Enforce final invariants", description: "Validate the profile, evidence, coverage results and required identifiers." },
    { title: "Evaluate blocking issues", description: "Separate warnings from errors that prevent a safe review handoff." },
    { title: "Set review readiness", description: "Record the final status, boolean decision and clear reasons." },
  ] },
  { id: "persistence", phase: "finalization", label: "Persistence", summary: "Writes the immutable Phase 15 finalization snapshot.", completion: "final_persistence_completed", metrics: ["finalization_run_id"], tasks: [
    { title: "Assemble final snapshot", description: "Combine profile, fields, requirements, evidence and validation results." },
    { title: "Write durable records", description: "Persist the immutable finalization run and its related data." },
    { title: "Store output identifiers", description: "Return stable IDs that the review workflow can load safely." },
  ] },
  { id: "review_handoff", phase: "finalization", label: "Review interrupt", summary: "Creates the review package, pauses LangGraph, then resumes with the human decision.", completion: "review_handoff_completed", interrupt: true, metrics: ["review_session_id", "review_status", "review_decision", "review_correction_count"], tasks: [
    { title: "Create the review package", description: "Prepare fields, requirements, evidence, warnings and corrections for the Review Agent and UI." },
    { title: "Pause with LangGraph interrupt", description: "Checkpoint the thread and wait without repeating completed extraction work." },
    { title: "Resume the human decision", description: "Apply approval or corrections and complete the handoff state." },
  ] },
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

  if (run.failed_node === node.id) return "failed";
  if (run.completed_nodes?.includes(node.id)) return "complete";
  if (run.skipped_nodes?.includes(node.id)) return "skipped";
  if (run.operation_status === "awaiting_review" && node.id === "review_handoff") return "review";
  if (run.current_node === node.id) return "running";
  if (run.next_nodes?.includes(node.id)) return "waiting";

  return "idle";
};
