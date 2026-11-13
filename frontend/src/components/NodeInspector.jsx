import { ArrowRight, Check, GitFork, Info, X } from "lucide-react";
import { getNodeStatus, phases, workflowEdges, workflowNodes } from "../data/workflow.js";
import { StatusPill } from "./StatusPill.jsx";

const display = (value) => {
  if (value === null || value === undefined || value === "") return "—";
  if (Array.isArray(value)) return value.length ? value.join(", ") : "[]";
  if (typeof value === "object") return JSON.stringify(value, null, 2);
  return String(value);
};

export function NodeInspector({ nodeId, run, onClose }) {
  const node = workflowNodes.find((item) => item.id === nodeId) || workflowNodes[0];
  const phase = phases.find((item) => item.id === node.phase);
  const incoming = workflowEdges.filter((edge) => edge.target === node.id);
  const outgoing = workflowEdges.filter((edge) => edge.source === node.id);
  const status = getNodeStatus(node, run);
  return (
    <section className="panel inspector">
      <div className="inspector-accent" style={{ background: phase.color }} />
      <div className="panel-heading"><div><p className="eyebrow">NODE INSPECTOR · {phase.label}</p><h2>{node.label}</h2></div><button className="icon-button" onClick={onClose} aria-label="Close inspector"><X size={17} /></button></div>
      <div className="inspector-status"><code>{node.id}</code><StatusPill status={status} /></div>
      <p className="node-summary">{node.summary}</p>
      {node.interrupt && <div className="callout"><Info size={16} /><span>This node persists the review package before calling <code>interrupt()</code>. Resume uses the same thread and does not restart extraction.</span></div>}
      <h3>Observed state</h3>
      <div className="metric-list">
        {node.metrics.map((metric) => <div className="metric-row" key={metric}><code>{metric}</code><span>{display(run?.[metric])}</span></div>)}
      </div>
      <h3>Incoming conditions</h3>
      <div className="edge-list">{incoming.length ? incoming.map((edge) => <div key={`${edge.source}-${edge.target}`}><GitFork size={14} /><code>{edge.source}</code><ArrowRight size={13} /><span>{edge.condition}</span></div>) : <p>Graph entry point</p>}</div>
      <h3>Outgoing decisions</h3>
      <div className="edge-list">{outgoing.length ? outgoing.map((edge) => { const chosen = run?.next_nodes?.includes(edge.target); return <div className={chosen ? "edge-chosen" : ""} key={`${edge.source}-${edge.target}`}>
        {chosen ? <Check size={14} /> : <GitFork size={14} />}<span>{edge.condition}</span><ArrowRight size={13} /><code>{edge.target}</code>
      </div>; }) : <div><Check size={14} /><span>Graph ends after reviewer decision</span></div>}</div>
    </section>
  );
}
