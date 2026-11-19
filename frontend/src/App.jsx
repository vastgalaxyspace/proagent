import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Activity, AlertCircle, ArrowRight, Check, CheckCircle2, Circle,
  ClipboardCheck, Cpu, DollarSign, Download, FileText, Loader2, Pause, Play, RotateCcw, Square,
  UploadCloud, X,
} from "lucide-react";
import { api } from "./lib/api.js";
import { getNodeStatus, workflowNodes } from "./data/workflow.js";
import { ReviewPanel } from "./components/ReviewPanel.jsx";

const defaultHeaders = { tenantId: "demo-tenant", userId: "developer" };

const loadSavedRun = () => {
  try {
    const saved = JSON.parse(localStorage.getItem("proagent.run") || "null");
    if (saved?.threadId && saved?.headers?.tenantId && saved?.headers?.userId) return saved;
  } catch {
    // Ignore invalid browser storage and show the upload screen.
  }
  const legacyThreadId = localStorage.getItem("proagent.threadId");
  return legacyThreadId ? { threadId: legacyThreadId, headers: defaultHeaders } : null;
};

const pretty = (value) => {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (Array.isArray(value)) return value.length ? value.join(", ") : "None";
  if (typeof value === "object") return JSON.stringify(value, null, 2);
  if (typeof value === "number" && !Number.isInteger(value)) return value.toFixed(3);
  return String(value);
};

const statusLabel = {
  complete: "Complete", running: "Working", waiting: "Next",
  failed: "Failed", skipped: "Skipped", review: "Needs review", idle: "Waiting",
};

function StatusIcon({ status }) {
  if (status === "complete") return <Check size={13} />;
  if (status === "running") return <Loader2 className="spin" size={13} />;
  if (status === "review") return <ClipboardCheck size={13} />;
  if (status === "failed") return <AlertCircle size={13} />;
  return <Circle size={10} />;
}

function UploadScreen({ readiness, onLaunch, onAttach, busy, error }) {
  const inputRef = useRef(null);
  const [title, setTitle] = useState("");
  const [reference, setReference] = useState("");
  const [files, setFiles] = useState([]);
  const [headers, setHeaders] = useState(defaultHeaders);
  const [threadId, setThreadId] = useState("");
  const [dragging, setDragging] = useState(false);

  const addFiles = (nextFiles) => {
    const incoming = Array.from(nextFiles || []);
    setFiles((current) => {
      const known = new Set(current.map((file) => `${file.name}:${file.size}`));
      return [...current, ...incoming.filter((file) => !known.has(`${file.name}:${file.size}`))];
    });
  };

  const submit = (event) => {
    event.preventDefault();
    onLaunch({ title: title.trim(), reference: reference.trim(), files, headers });
  };

  return (
    <div className="upload-page">
      <header className="upload-header">
        <div className="brand"><span>PA</span><strong>Procurement Agent</strong></div>
        <div className={`connection ${readiness?.status === "ready" ? "online" : "offline"}`}>
          <i /> {readiness?.status === "ready" ? "Backend ready" : "Backend unavailable"}
        </div>
      </header>

      <main className="upload-main">
        <div className="intro">
          <span className="kicker">NEW ANALYSIS</span>
          <h1>Upload tender documents</h1>
          <p>Add the source files and the agent will extract, understand, validate, and prepare them for review.</p>
        </div>

        <form className="upload-card" onSubmit={submit}>
          <div className="field-grid">
            <label>
              Tender title <b>Required</b>
              <input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="Example: City surveillance platform" />
            </label>
            <label>
              Reference <span>Optional</span>
              <input value={reference} onChange={(event) => setReference(event.target.value)} placeholder="RFP or tender reference" />
            </label>
          </div>

          <button
            className={`drop-zone ${dragging ? "dragging" : ""}`}
            type="button"
            onClick={() => inputRef.current?.click()}
            onDragOver={(event) => { event.preventDefault(); setDragging(true); }}
            onDragLeave={() => setDragging(false)}
            onDrop={(event) => { event.preventDefault(); setDragging(false); addFiles(event.dataTransfer.files); }}
          >
            <input ref={inputRef} type="file" multiple hidden onChange={(event) => addFiles(event.target.files)} />
            <span className="upload-icon"><UploadCloud size={25} /></span>
            <strong>Drop documents here</strong>
            <small>or click to browse · PDF, DOCX, XLSX, text, and ZIP</small>
          </button>

          {files.length > 0 && (
            <div className="file-list">
              {files.map((file) => (
                <div className="file-row" key={`${file.name}:${file.size}`}>
                  <FileText size={17} />
                  <div><strong>{file.name}</strong><span>{(file.size / 1024 / 1024).toFixed(2)} MB</span></div>
                  <button type="button" aria-label={`Remove ${file.name}`} onClick={() => setFiles((items) => items.filter((item) => item !== file))}><X size={15} /></button>
                </div>
              ))}
            </div>
          )}

          <details className="advanced">
            <summary>Connection settings</summary>
            <div className="field-grid compact">
              <label>Tenant ID<input value={headers.tenantId} onChange={(event) => setHeaders({ ...headers, tenantId: event.target.value })} /></label>
              <label>User ID<input value={headers.userId} onChange={(event) => setHeaders({ ...headers, userId: event.target.value })} /></label>
            </div>
          </details>

          {error && <div className="form-error"><AlertCircle size={16} />{error}</div>}

          <button className="launch-button" disabled={busy || !title.trim() || files.length === 0} type="submit">
            {busy ? <Loader2 className="spin" size={17} /> : <Play size={17} fill="currentColor" />}
            {busy ? "Creating tender…" : "Start analysis"}
            {!busy && <ArrowRight size={17} />}
          </button>
        </form>

        <div className="resume-row">
          <span>Already have a run?</span>
          <input value={threadId} onChange={(event) => setThreadId(event.target.value)} placeholder="Paste LangGraph thread ID" />
          <button disabled={!threadId.trim()} onClick={() => onAttach(threadId.trim(), headers)}>Open run</button>
        </div>
      </main>
    </div>
  );
}

function RunScreen({ readiness, run, threadId, headers, starting, error, onReset, onControl, onRerun, onDownloadProblems, onRefresh, replayableNodes, controlBusy }) {
  const [selectedNodeId, setSelectedNodeId] = useState(null);
  const visibleRun = useMemo(() => {
    if (!run) return run;
    const activeStatuses = ["queued", "running", "pause_requested", "cancel_requested"];
    const activeNodeId = activeStatuses.includes(run.operation_status)
      ? run.next_nodes?.[0] || run.current_node
      : run.current_node;
    return { ...run, current_node: activeNodeId };
  }, [run]);
  const nodeStates = useMemo(() => workflowNodes.map((node) => ({ node, status: getNodeStatus(node, visibleRun) })), [visibleRun]);
  const liveNode = useMemo(() => {
    if (!visibleRun) return workflowNodes[0];
    const id = (
      visibleRun.failed_node
      || visibleRun.current_node
      || visibleRun.next_nodes?.[0]
    );
    return workflowNodes.find((node) => node.id === id)
      || [...nodeStates].reverse().find((item) => item.status === "complete")?.node
      || workflowNodes[0];
  }, [visibleRun, nodeStates]);
  const activeNode = workflowNodes.find((node) => node.id === selectedNodeId) || liveNode;
  const activeStatus = starting && !visibleRun && activeNode.id === liveNode.id ? "running" : getNodeStatus(activeNode, visibleRun);
  const liveStatus = starting && !visibleRun ? "running" : getNodeStatus(liveNode, visibleRun);
  const completeCount = nodeStates.filter((item) => item.status === "complete").length;
  const skippedCount = nodeStates.filter((item) => item.status === "skipped").length;
  const processedCount = completeCount + skippedCount;
  const progress = Math.round((processedCount / workflowNodes.length) * 100);
  const metrics = activeNode.metrics || [];
  const operationStatus = run?.operation_status || (starting ? "queued" : "unknown");
  const canPause = ["queued", "running"].includes(operationStatus);
  const canResume = operationStatus === "paused";
  const canCancel = ["queued", "running", "pause_requested", "paused", "cancel_requested"].includes(operationStatus);
  const operationLabel = operationStatus.replaceAll("_", " ");
  const executingNode = ["running", "pause_requested", "cancel_requested"].includes(operationStatus);
  const nodeActivityLabel = operationStatus === "pause_requested"
    ? "PAUSE REQUESTED · FINISHING CURRENT NODE"
    : operationStatus === "cancel_requested"
      ? "CANCEL REQUESTED · FINISHING CURRENT NODE"
      : "CURRENTLY RUNNING";
  const canRerunSelected = Boolean(
    selectedNodeId && replayableNodes.includes(selectedNodeId)
  );
  const problemEvents = useMemo(() => {
    if (run?.problem_events?.length) return run.problem_events;
    return [
      ...(run?.warnings || []).map((message) => ({ node: null, severity: "warning", message })),
      ...(run?.errors || []).map((message) => ({ node: run?.failed_node || null, severity: "error", message })),
    ];
  }, [run]);
  const aiUsage = run?.ai_usage || {};
  const totalTokens = Number(aiUsage.total_tokens || 0);
  const estimatedCost = aiUsage.estimated_cost_usd;
  const usageHeadline = estimatedCost !== null && estimatedCost !== undefined
    ? `$${Number(estimatedCost).toFixed(6)}`
    : `${totalTokens.toLocaleString()} tokens`;
  const usageDetail = totalTokens > 0
    ? `${Number(aiUsage.input_tokens || 0).toLocaleString()} input · ${Number(aiUsage.output_tokens || 0).toLocaleString()} output · ${Number(aiUsage.request_count || 0).toLocaleString()} requests${aiUsage.pricing_configured ? "" : " · pricing not configured"}`
    : "No provider usage received yet";

  return (
    <div className="run-page">
      <header className="run-header">
        <div>
          <div className="brand"><span>PA</span><strong>Procurement Agent</strong></div>
          <p className="run-id">{threadId || "Preparing run…"}</p>
        </div>
        <div className="header-summary">
          <div className="model-chip"><Cpu size={15} /><span>Model<strong>{readiness?.main_llm_model || "Not reported"}</strong></span></div>
          <div className="cost-chip"><DollarSign size={15} /><span>AI usage<strong>{usageHeadline}</strong><small>{usageDetail}</small></span></div>
          <div className="run-controls" aria-label="Agent controls">
            {canPause && <button className="run-control pause" disabled={Boolean(controlBusy)} onClick={() => onControl("pause")}><Pause size={14} />{controlBusy === "pause" ? "Pausing…" : "Pause"}</button>}
            {operationStatus === "pause_requested" && <button className="run-control pause" disabled><Loader2 className="spin" size={14} />Pausing…</button>}
            {canResume && <button className="run-control resume" disabled={Boolean(controlBusy)} onClick={() => onControl("resume")}><Play size={14} />{controlBusy === "resume" ? "Resuming…" : "Resume"}</button>}
            {canCancel && <button className="run-control cancel" disabled={Boolean(controlBusy) || operationStatus === "cancel_requested"} onClick={() => onControl("cancel")}><Square size={12} fill="currentColor" />{operationStatus === "cancel_requested" || controlBusy === "cancel" ? "Cancelling…" : "Cancel"}</button>}
          </div>
          <button className="new-run" onClick={onReset}><RotateCcw size={15} />New tender</button>
        </div>
      </header>

      <div className="run-layout">
        <aside className="node-sidebar">
          <div className="progress-heading">
            <div>
              <span>WORKFLOW</span>
              <strong>
                {completeCount} complete
                {skippedCount > 0 ? ` · ${skippedCount} skipped` : ""}
                {` · ${workflowNodes.length} total`}
              </strong>
            </div>
            <b>{progress}%</b>
          </div>
          <div className="progress-track"><i style={{ width: `${progress}%` }} /></div>
          <nav className="node-list" aria-label="Workflow nodes">
            {nodeStates.map(({ node, status }, index) => (
              <button
                type="button"
                className={`node-item ${status} ${activeNode.id === node.id ? "selected" : ""}`}
                key={node.id}
                onClick={() => setSelectedNodeId(node.id)}
                aria-pressed={activeNode.id === node.id}
                aria-label={`Open ${node.label} node details`}
              >
                <span className="node-number"><StatusIcon status={status} /></span>
                <div><small>STEP {String(index + 1).padStart(2, "0")}</small><strong>{node.label}</strong></div>
                <em>{statusLabel[status]}</em>
              </button>
            ))}
          </nav>
        </aside>

        <main className="node-workspace">
          <div className="workspace-topline">
            <div className={`live-status ${operationStatus}`}><Activity size={14} />{starting && !run ? "Starting agent" : operationLabel}</div>
            <div className="backend-status"><i className={readiness?.status === "ready" ? "online" : ""} />Backend {readiness?.status || "unknown"}</div>
          </div>

          {error && <div className="run-error"><AlertCircle size={17} /><div><strong>Run error</strong><span>{error}</span></div></div>}
          {run?.control_message && operationStatus === "paused" && (
            <div className="run-notice"><Pause size={17} /><div><strong>Run paused</strong><span>{run.control_message}</span></div></div>
          )}
          {operationStatus === "awaiting_review" && (
            <div className="review-waiting-strip">
              <span><ClipboardCheck size={19} /></span>
              <div><small>HUMAN DECISION REQUIRED</small><strong>This node is waiting for your review—it is not still processing.</strong></div>
            </div>
          )}
          {executingNode && (
            <div className={`current-node-strip ${operationStatus}`}>
              <span className="current-node-spinner"><Loader2 className="spin" size={18} /></span>
              <div>
                <small>{nodeActivityLabel}</small>
                <strong>{liveNode.label}</strong>
                <code>{liveNode.id}</code>
              </div>
            </div>
          )}

          {operationStatus === "awaiting_review" && (
            <ReviewPanel run={run} threadId={threadId} headers={headers} onCompleted={onRefresh} />
          )}

          <section className="active-node-card">
            <div className="node-card-header">
              <span className={`large-node-icon ${activeStatus}`}><StatusIcon status={activeStatus} /></span>
              <div><p>{selectedNodeId ? "SELECTED NODE" : "CURRENT NODE"}</p><h1>{activeNode.label}</h1><code>{activeNode.id}</code></div>
              {selectedNodeId && (
                <div className="node-card-actions">
                  {canRerunSelected && (
                    <button className="rerun-node-button" type="button" disabled={Boolean(controlBusy)} onClick={() => onRerun(selectedNodeId)}>
                      <RotateCcw size={13} />{controlBusy === "rerun" ? "Starting…" : "Rerun from here"}
                    </button>
                  )}
                  <button className="follow-live-button" type="button" onClick={() => setSelectedNodeId(null)}>
                    <Activity size={13} /> Follow live node
                  </button>
                </div>
              )}
            </div>
            <p className="node-description">{activeNode.summary}</p>
            <div className="task-heading"><span>WHAT THIS NODE DOES</span><small>{activeNode.tasks?.length || 0} tasks</small></div>
            <div className="step-list">
              {(activeNode.tasks || []).map((task, index) => (
                <div className={`step-row node-task-row ${activeStatus === "complete" ? "done" : activeStatus === "running" ? "active" : ""}`} key={task.title}>
                  <span>{activeStatus === "complete" ? <CheckCircle2 size={17} /> : <b>{index + 1}</b>}</span>
                  <div><strong>{task.title}</strong><p>{task.description}</p></div>
                </div>
              ))}
            </div>
          </section>

          <section className="output-card">
            <div className="section-heading"><div><span>LIVE OUTPUT</span><h2>What this node produced</h2></div><small>Updates automatically</small></div>
            {metrics.length ? (
              <div className="metric-grid">
                {metrics.map((key) => <div className="metric" key={key}><span>{key.replaceAll("_", " ")}</span><strong>{pretty(run?.[key])}</strong></div>)}
              </div>
            ) : <p className="empty-output">This node has no reportable output yet.</p>}
          </section>

          {(problemEvents.length > 0 || run?.problem_report_available) && (
            <section className="messages-card">
              <div className="problem-heading">
                <div><span>RUN PROBLEMS</span><h2>Warnings and errors from every node</h2></div>
                {run?.problem_report_available && (
                  <button type="button" disabled={controlBusy === "download"} onClick={onDownloadProblems}>
                    {controlBusy === "download" ? <Loader2 className="spin" size={14} /> : <Download size={14} />}
                    {controlBusy === "download" ? "Preparing…" : "Download JSON"}
                  </button>
                )}
              </div>
              <div className="problem-list">
                {problemEvents.map((problem, index) => (
                  <div className={`problem-row ${problem.severity}`} key={`${problem.node || "run"}-${problem.severity}-${index}-${problem.message}`}>
                    <AlertCircle size={15} />
                    <div><small>{problem.node || "Run"} · {problem.severity}</small><p>{problem.message}</p></div>
                  </div>
                ))}
                {problemEvents.length === 0 && <p className="no-problems">No warnings or errors were recorded.</p>}
              </div>
            </section>
          )}
        </main>
      </div>
    </div>
  );
}

export default function App() {
  const restoredRun = useMemo(loadSavedRun, []);
  const [screen, setScreen] = useState(restoredRun ? "run" : "upload");
  const [readiness, setReadiness] = useState(null);
  const [headers, setHeaders] = useState(restoredRun?.headers || defaultHeaders);
  const [threadId, setThreadId] = useState(restoredRun?.threadId || "");
  const [run, setRun] = useState(null);
  const [busy, setBusy] = useState(false);
  const [starting, setStarting] = useState(false);
  const [controlBusy, setControlBusy] = useState("");
  const [replayableNodes, setReplayableNodes] = useState([]);
  const [error, setError] = useState("");

  const checkReadiness = useCallback(() => {
    api.readiness().then((value) => { setReadiness(value); if (screen === "upload") setError(""); }).catch((reason) => {
      setReadiness(null);
      if (screen === "upload") setError(`Backend unavailable: ${reason.message}`);
    });
  }, [screen]);

  useEffect(() => {
    checkReadiness();
    const timer = window.setInterval(checkReadiness, 10000);
    return () => window.clearInterval(timer);
  }, [checkReadiness]);

  const refresh = useCallback(async () => {
    if (!threadId) return;
    try {
      const next = await api.getRun(threadId, headers);
      setRun(next);
      if (["queued", "running", "pause_requested", "cancel_requested"].includes(next.operation_status)) {
        setReplayableNodes([]);
      } else {
        const options = await api.getReplayOptions(threadId, headers);
        setReplayableNodes(options.nodes.map((item) => item.node_name));
      }
      setError("");
    } catch (reason) { setError(reason.message); }
  }, [threadId, headers]);

  useEffect(() => {
    if (screen !== "run" || !threadId) return undefined;
    refresh();
    const timer = window.setInterval(refresh, 1500);
    return () => window.clearInterval(timer);
  }, [screen, threadId, refresh]);

  const launch = async ({ title, reference, files, headers: nextHeaders }) => {
    setBusy(true); setError(""); setHeaders(nextHeaders);
    try {
      const tender = await api.createTender({ title, reference, files, headers: nextHeaders });
      setScreen("run"); setStarting(true);
      const accepted = await api.startRun(tender.tender_id, nextHeaders);
      setThreadId(accepted.thread_id);
      localStorage.setItem("proagent.threadId", accepted.thread_id);
      localStorage.setItem("proagent.run", JSON.stringify({ threadId: accepted.thread_id, headers: nextHeaders }));
    } catch (reason) {
      setError(reason.message);
      setScreen("upload");
    } finally { setBusy(false); setStarting(false); }
  };

  const attach = (nextThreadId, nextHeaders) => {
    setHeaders(nextHeaders); setThreadId(nextThreadId); setRun(null); setError(""); setScreen("run");
    localStorage.setItem("proagent.threadId", nextThreadId);
    localStorage.setItem("proagent.run", JSON.stringify({ threadId: nextThreadId, headers: nextHeaders }));
  };

  const controlRun = async (action) => {
    if (!threadId || controlBusy) return;
    if (action === "cancel" && !window.confirm("Cancel this agent run? Completed node results will remain stored.")) return;
    setControlBusy(action); setError("");
    try {
      if (action === "pause") await api.pauseRun(threadId, headers);
      if (action === "resume") await api.resumeRun(threadId, headers);
      if (action === "cancel") await api.cancelRun(threadId, headers);
      await refresh();
    } catch (reason) { setError(reason.message); }
    finally { setControlBusy(""); }
  };

  const rerunFromNode = async (nodeName) => {
    if (!threadId || controlBusy) return;
    if (!window.confirm(`Rerun from ${nodeName}? Results from this node onward will be produced again.`)) return;
    setControlBusy("rerun"); setError("");
    try {
      await api.rerunFromNode(threadId, nodeName, headers);
      setReplayableNodes([]);
      await refresh();
    } catch (reason) { setError(reason.message); }
    finally { setControlBusy(""); }
  };

  const downloadProblems = async () => {
    if (!threadId || controlBusy) return;
    setControlBusy("download"); setError("");
    try {
      const { blob, fileName } = await api.downloadProblemReport(threadId, headers);
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url; anchor.download = fileName; anchor.click();
      URL.revokeObjectURL(url);
    } catch (reason) { setError(reason.message); }
    finally { setControlBusy(""); }
  };

  const reset = () => {
    setScreen("upload"); setThreadId(""); setRun(null); setStarting(false); setControlBusy(""); setReplayableNodes([]); setError("");
    localStorage.removeItem("proagent.threadId");
    localStorage.removeItem("proagent.run");
  };

  return screen === "upload"
    ? <UploadScreen readiness={readiness} onLaunch={launch} onAttach={attach} busy={busy} error={error} />
    : <RunScreen readiness={readiness} run={run} threadId={threadId} headers={headers} starting={starting} error={error} onReset={reset} onControl={controlRun} onRerun={rerunFromNode} onDownloadProblems={downloadProblems} onRefresh={refresh} replayableNodes={replayableNodes} controlBusy={controlBusy} />;
}
