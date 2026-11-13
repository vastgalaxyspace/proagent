import { Clock3, Radio } from "lucide-react";

export function EventTimeline({ events }) {
  return (
    <section className="panel timeline-panel">
      <div className="panel-heading"><div><p className="eyebrow">LOCAL OBSERVATION LOG</p><h2>State transitions</h2></div><Radio size={17} /></div>
      <div className="timeline">
        {events.length ? events.map((event) => <article key={event.id}><span className="timeline-dot" /><div><div className="timeline-meta"><code>{event.node}</code><time><Clock3 size={11} />{event.time.toLocaleTimeString()}</time></div><p>{event.message}</p><span className="muted">operation: {event.status}</span></div></article>) : <div className="empty-state">Attach a run to begin recording state changes in this browser.</div>}
      </div>
    </section>
  );
}
