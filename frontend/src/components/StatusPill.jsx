const labels = { complete: "Complete", running: "Running", waiting: "Next", failed: "Failed", skipped: "Skipped", idle: "Pending", active: "Active" };

export function StatusPill({ status, children }) {
  return <span className={`status-pill status-${status}`}><span className="status-dot" />{children || labels[status] || status}</span>;
}
