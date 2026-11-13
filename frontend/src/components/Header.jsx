import { Activity, Database, Radio, Wifi, WifiOff } from "lucide-react";

export function Header({ readiness, backendError, polling }) {
  return (
    <header className="topbar">
      <div className="brand-mark"><Activity size={20} /></div>
      <div>
        <p className="eyebrow">PROAGENT / DEVELOPER CONSOLE</p>
        <h1>Tender Agent Observatory</h1>
      </div>
      <div className="topbar-spacer" />
      <div className="health-strip">
        <span className={backendError ? "health bad" : "health good"}>{backendError ? <WifiOff size={14} /> : <Wifi size={14} />} API {backendError ? "offline" : "connected"}</span>
        <span className="health"><Database size={14} /> {readiness?.database || "checking"}</span>
        <span className={`health ${polling ? "live" : ""}`}><Radio size={14} /> {polling ? "live polling" : "polling paused"}</span>
      </div>
    </header>
  );
}
