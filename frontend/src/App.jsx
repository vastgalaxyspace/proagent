import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertCircle, Pause, Play, RefreshCw } from "lucide-react";
import { Header } from "./components/Header.jsx";
import { SetupPanel } from "./components/SetupPanel.jsx";
import { RunOverview } from "./components/RunOverview.jsx";
import { WorkflowCanvas } from "./components/WorkflowCanvas.jsx";
import { NodeInspector } from "./components/NodeInspector.jsx";
import { EventTimeline } from "./components/EventTimeline.jsx";
import { StateViewer } from "./components/StateViewer.jsx";
import { ReviewPanel } from "./components/ReviewPanel.jsx";
import { api } from "./lib/api.js";
import { useRunMonitor } from "./hooks/useRunMonitor.js";

export default function App() {
  const [headers, setHeadersState] = useState(() => ({
    tenantId: localStorage.getItem("proagent.tenantId") || "demo-tenant",
    userId: localStorage.getItem("proagent.userId") || "developer",
  }));
  const setHeaders = useCallback((updater) => setHeadersState((current) => {
    const next = typeof updater === "function" ? updater(current) : updater;
    localStorage.setItem("proagent.tenantId", next.tenantId);
    localStorage.setItem("proagent.userId", next.userId);
    return next;
  }), []);
  const stableHeaders = useMemo(() => headers, [headers.tenantId, headers.userId]);
  const monitor = useRunMonitor(stableHeaders);
  const [readiness, setReadiness] = useState(null);
  const [backendError, setBackendError] = useState("");
  const [selectedNode, setSelectedNode] = useState("load_context");
  const [showInspector, setShowInspector] = useState(true);

  useEffect(() => {
    const check = () => api.readiness().then((data) => { setReadiness(data); setBackendError(""); }).catch((err) => setBackendError(err.message));
    check(); const timer = window.setInterval(check, 10000); return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    if (monitor.run?.current_node) { setSelectedNode(monitor.run.current_node); setShowInspector(true); }
    else if (monitor.run?.next_nodes?.[0]) { setSelectedNode(monitor.run.next_nodes[0]); setShowInspector(true); }
  }, [monitor.run?.current_node, monitor.run?.next_nodes]);

  return (
    <div className="app-shell">
      <Header readiness={readiness} backendError={backendError} polling={monitor.polling} />
      <main>
        <aside className="left-rail"><SetupPanel headers={headers} setHeaders={setHeaders} threadId={monitor.threadId} onAttach={monitor.attach} /><EventTimeline events={monitor.events} /></aside>
        <div className="workspace">
          <div className="run-toolbar">
            <div><p className="eyebrow">ACTIVE THREAD</p><code>{monitor.threadId || "No run attached"}</code></div>
            <div className="toolbar-actions"><button className="button ghost" onClick={monitor.refresh} disabled={!monitor.threadId}><RefreshCw size={15} /> Refresh</button><button className="button ghost" onClick={() => monitor.setPolling((value) => !value)} disabled={!monitor.threadId}>{monitor.polling ? <Pause size={15} /> : <Play size={15} />}{monitor.polling ? "Pause" : "Resume"}</button></div>
          </div>
          {(monitor.error || backendError) && <div className="global-error"><AlertCircle size={17} /><span>{monitor.error || backendError}</span></div>}
          <RunOverview run={monitor.run} />
          <div className={`graph-layout ${showInspector ? "with-inspector" : ""}`}><WorkflowCanvas run={monitor.run} selectedNode={selectedNode} onSelect={(id) => { setSelectedNode(id); setShowInspector(true); }} />{showInspector && <NodeInspector nodeId={selectedNode} run={monitor.run} onClose={() => setShowInspector(false)} />}</div>
          <ReviewPanel run={monitor.run} threadId={monitor.threadId} headers={stableHeaders} onCompleted={monitor.refresh} />
          <StateViewer run={monitor.run} />
        </div>
      </main>
    </div>
  );
}
