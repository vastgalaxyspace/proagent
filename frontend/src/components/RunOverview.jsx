import { AlertTriangle, Boxes, CheckCircle2, CircleGauge, GitBranch, PauseCircle } from "lucide-react";
import { modeCards } from "../data/workflow.js";
import { StatusPill } from "./StatusPill.jsx";

export function RunOverview({ run }) {
  const stats = [
    { label: "Workflow", value: run?.workflow_status || "not attached", icon: GitBranch },
    { label: "Current node", value: run?.current_node || "—", icon: Boxes },
    { label: "Readiness", value: run ? `${Math.round(run.readiness_score || 0)}%` : "—", icon: CircleGauge },
    { label: "Review items", value: (run?.coverage_issue_count || 0) + (run?.review_requirement_count || 0), icon: AlertTriangle },
  ];
  return (
    <>
      <section className="stat-grid">
        {stats.map(({ label, value, icon: Icon }) => <article className="stat-card" key={label}><Icon size={17} /><div><p>{label}</p><strong>{String(value).replaceAll("_", " ")}</strong></div></article>)}
      </section>
      <section className="mode-grid">
        {modeCards.map((mode) => { const state = mode.state(run); return <article className={`mode-card mode-${state}`} key={mode.key}><div className="mode-icon">{state === "complete" ? <CheckCircle2 size={17} /> : state === "active" ? <PauseCircle size={17} /> : <span />}</div><div><strong>{mode.key} mode</strong><p>{mode.description}</p></div><StatusPill status={state} /></article>; })}
      </section>
    </>
  );
}
