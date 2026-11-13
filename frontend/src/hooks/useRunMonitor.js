import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../lib/api.js";

const signature = (run) => [run?.operation_status, run?.workflow_status, run?.current_node, ...(run?.next_nodes || [])].join("|");

export function useRunMonitor(headers) {
  const [threadId, setThreadId] = useState(() => localStorage.getItem("proagent.threadId") || "");
  const [run, setRun] = useState(null);
  const [events, setEvents] = useState([]);
  const [polling, setPolling] = useState(true);
  const [error, setError] = useState("");
  const lastSignature = useRef("");

  const attach = useCallback((value) => {
    const normalized = value.trim();
    setThreadId(normalized);
    if (normalized) localStorage.setItem("proagent.threadId", normalized);
    else localStorage.removeItem("proagent.threadId");
    setRun(null);
    setEvents([]);
    lastSignature.current = "";
  }, []);

  const refresh = useCallback(async () => {
    if (!threadId) return;
    try {
      const next = await api.getRun(threadId, headers);
      const nextSignature = signature(next);
      if (nextSignature !== lastSignature.current) {
        setEvents((current) => [{
          id: `${Date.now()}-${nextSignature}`,
          time: new Date(),
          node: next.current_node || next.next_nodes?.[0] || "graph",
          status: next.operation_status,
          message: next.next_nodes?.length
            ? `Edge selected → ${next.next_nodes.join(", ")}`
            : `Workflow state changed to ${next.workflow_status}`,
        }, ...current].slice(0, 80));
        lastSignature.current = nextSignature;
      }
      setRun(next);
      setError("");
      if (next.completed) setPolling(false);
    } catch (err) {
      setError(err.message);
    }
  }, [headers, threadId]);

  useEffect(() => {
    refresh();
    if (!polling || !threadId) return undefined;
    const timer = window.setInterval(refresh, 2000);
    return () => window.clearInterval(timer);
  }, [polling, refresh, threadId]);

  return { threadId, attach, run, events, polling, setPolling, refresh, error };
}
