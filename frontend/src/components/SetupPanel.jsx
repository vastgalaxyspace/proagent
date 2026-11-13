import { useState } from "react";
import { FileUp, LoaderCircle, Play, PlugZap } from "lucide-react";
import { api } from "../lib/api.js";

export function SetupPanel({ headers, setHeaders, threadId, onAttach }) {
  const [title, setTitle] = useState("");
  const [reference, setReference] = useState("");
  const [files, setFiles] = useState([]);
  const [tenderId, setTenderId] = useState("");
  const [manualThread, setManualThread] = useState(threadId);
  const [busy, setBusy] = useState("");
  const [message, setMessage] = useState("");

  const create = async () => {
    if (!title || !files.length) return setMessage("Add a title and at least one document.");
    setBusy("create"); setMessage("");
    try {
      const result = await api.createTender({ title, reference, files, headers });
      setTenderId(result.tender_id);
      setMessage(`Created tender ${result.tender_id.slice(0, 8)} with ${result.documents.length} document(s).`);
    } catch (err) { setMessage(err.message); } finally { setBusy(""); }
  };

  const start = async () => {
    if (!tenderId) return setMessage("Create a tender or paste its ID first.");
    setBusy("start"); setMessage("");
    try {
      const result = await api.startRun(tenderId, headers);
      setManualThread(result.thread_id);
      onAttach(result.thread_id);
      setMessage("Run started and attached to the live monitor.");
    } catch (err) { setMessage(err.message); } finally { setBusy(""); }
  };

  return (
    <section className="panel setup-panel">
      <div className="panel-heading"><div><p className="eyebrow">CONNECTION & RUN</p><h2>Launch or attach</h2></div><PlugZap size={18} /></div>
      <div className="form-grid two">
        <label>Tenant ID<input value={headers.tenantId} onChange={(e) => setHeaders((h) => ({ ...h, tenantId: e.target.value }))} /></label>
        <label>User ID<input value={headers.userId} onChange={(e) => setHeaders((h) => ({ ...h, userId: e.target.value }))} /></label>
      </div>
      <div className="divider" />
      <label>Tender title<input placeholder="e.g. City surveillance platform" value={title} onChange={(e) => setTitle(e.target.value)} /></label>
      <label>External reference<input placeholder="Optional reference" value={reference} onChange={(e) => setReference(e.target.value)} /></label>
      <label className="file-drop"><FileUp size={18} /><span>{files.length ? `${files.length} file(s) selected` : "Choose tender documents"}</span><input type="file" multiple onChange={(e) => setFiles([...e.target.files])} /></label>
      <button className="button secondary" onClick={create} disabled={!!busy}>{busy === "create" ? <LoaderCircle className="spin" size={16} /> : <FileUp size={16} />} Create tender</button>
      <div className="inline-action"><input placeholder="Tender UUID" value={tenderId} onChange={(e) => setTenderId(e.target.value)} /><button className="button primary" onClick={start} disabled={!!busy}>{busy === "start" ? <LoaderCircle className="spin" size={16} /> : <Play size={16} />} Run</button></div>
      <div className="divider"><span>OR ATTACH</span></div>
      <div className="inline-action"><input placeholder="LangGraph thread ID" value={manualThread} onChange={(e) => setManualThread(e.target.value)} /><button className="button ghost" onClick={() => onAttach(manualThread)}>Attach</button></div>
      {message && <p className="form-message">{message}</p>}
    </section>
  );
}
