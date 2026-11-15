import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Activity, AlertCircle, ArrowRight, Check, CheckCircle2, Circle,
  Cpu, DollarSign, FileText, Loader2, Play, RotateCcw,
  UploadCloud, X,
} from "lucide-react";
import { api } from "./lib/api.js";
import { getNodeStatus, workflowNodes } from "./data/workflow.js";

const defaultHeaders = { tenantId: "demo-tenant", userId: "developer" };

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
  failed: "Failed", skipped: "Skipped", idle: "Waiting",
};

function StatusIcon({ status }) {
  if (status === "complete") return <Check size={13} />;
  if (status === "running") return <Loader2 className="spin" size={13} />;
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

function RunScreen({ readiness, run, threadId, starting, error, onReset }) {
  const [selectedNodeId, setSelectedNodeId] = useState(null);
  const nodeStates = useMemo(() => workflowNodes.map((node) => ({ node, status: getNodeStatus(node, run) })), [run]);
  const liveNode = useMemo(() => {
    if (!run) return workflowNodes[0];
    const id = (
      run.failed_node
      || run.current_node
      || run.next_nodes?.[0]
    );
    return workflowNodes.find((node) => node.id === id)
      || [...nodeStates].reverse().find((item) => item.status === "complete")?.node
      || workflowNodes[0];
  }, [run, nodeStates]);
  const activeNode = workflowNodes.find((node) => node.id === selectedNodeId) || liveNode;
  const activeStatus = starting && !run && activeNode.id === liveNode.id ? "running" : getNodeStatus(activeNode, run);
  const liveStatus = starting && !run ? "running" : getNodeStatus(liveNode, run);
  const completeCount = nodeStates.filter((item) => item.status === "complete").length;
  const skippedCount = nodeStates.filter((item) => item.status === "skipped").length;
  const processedCount = completeCount + skippedCount;
  const progress = Math.round((processedCount / workflowNodes.length) * 100);
  const metrics = activeNode.metrics || [];

  return (
    <div className="run-page">
      <header className="run-header">
        <div>
          <div className="brand"><span>PA</span><strong>Procurement Agent</strong></div>
          <p className="run-id">{threadId || "Preparing run…"}</p>
        </div>
        <div className="header-summary">
          <div className="model-chip"><Cpu size={15} /><span>Model<strong>{readiness?.main_llm_model || "Not reported"}</strong></span></div>
          <div className="cost-chip"><DollarSign size={15} /><span>Run cost<strong>Not reported</strong><small>API has no token usage yet</small></span></div>
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
            <div className={`live-status ${liveStatus}`}><Activity size={14} />{starting && !run ? "Starting agent" : statusLabel[liveStatus]}</div>
            <div className="backend-status"><i className={readiness?.status === "ready" ? "online" : ""} />Backend {readiness?.status || "unknown"}</div>
          </div>

          {error && <div className="run-error"><AlertCircle size={17} /><div><strong>Run error</strong><span>{error}</span></div></div>}

          <section className="active-node-card">
            <div className="node-card-header">
              <span className={`large-node-icon ${activeStatus}`}><StatusIcon status={activeStatus} /></span>
              <div><p>{selectedNodeId ? "SELECTED NODE" : "CURRENT NODE"}</p><h1>{activeNode.label}</h1><code>{activeNode.id}</code></div>
              {selectedNodeId && (
                <button className="follow-live-button" type="button" onClick={() => setSelectedNodeId(null)}>
                  <Activity size={13} /> Follow live node
                </button>
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

          {(run?.warnings?.length > 0 || run?.errors?.length > 0) && (
            <section className="messages-card">
              {run.errors?.map((message) => <p className="error-line" key={message}><AlertCircle size={15} />{message}</p>)}
              {run.warnings?.map((message) => <p className="warning-line" key={message}><AlertCircle size={15} />{message}</p>)}
            </section>
          )}
        </main>
      </div>
    </div>
  );
}

export default function App() {
  const [screen, setScreen] = useState("upload");
  const [readiness, setReadiness] = useState(null);
  const [headers, setHeaders] = useState(defaultHeaders);
  const [threadId, setThreadId] = useState("");
  const [run, setRun] = useState(null);
  const [busy, setBusy] = useState(false);
  const [starting, setStarting] = useState(false);
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
    } catch (reason) {
      setError(reason.message);
      setScreen("upload");
    } finally { setBusy(false); setStarting(false); }
  };

  const attach = (nextThreadId, nextHeaders) => {
    setHeaders(nextHeaders); setThreadId(nextThreadId); setRun(null); setError(""); setScreen("run");
  };

  const reset = () => {
    setScreen("upload"); setThreadId(""); setRun(null); setStarting(false); setError("");
    localStorage.removeItem("proagent.threadId");
  };

  return screen === "upload"
    ? <UploadScreen readiness={readiness} onLaunch={launch} onAttach={attach} busy={busy} error={error} />
    : <RunScreen readiness={readiness} run={run} threadId={threadId} starting={starting} error={error} onReset={reset} />;
}
