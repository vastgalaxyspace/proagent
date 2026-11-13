import { useEffect, useState } from "react";
import { CheckCircle2, ClipboardCheck, LoaderCircle, RotateCcw, ShieldAlert, XCircle } from "lucide-react";
import { api } from "../lib/api.js";

export function ReviewPanel({ run, threadId, headers, onCompleted }) {
  const [review, setReview] = useState(null);
  const [decision, setDecision] = useState("approved");
  const [comment, setComment] = useState("");
  const [correctionsText, setCorrectionsText] = useState("[]");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!threadId || !run?.review_session_id) return;
    api.getReview(threadId, headers).then((data) => {
      setReview(data);
      setCorrectionsText(JSON.stringify(data.corrections || [], null, 2));
    }).catch((err) => setError(err.message));
  }, [headers, run?.review_session_id, threadId]);

  if (!run || (!run.review_session_id && run.operation_status !== "awaiting_review")) return null;

  const submit = async () => {
    setBusy(true); setError("");
    try {
      const corrections = JSON.parse(correctionsText);
      await api.submitReview(threadId, { decision, comment: comment || null, corrections }, headers);
      await onCompleted();
      setReview(await api.getReview(threadId, headers));
    } catch (err) { setError(err.message); } finally { setBusy(false); }
  };

  const packageData = review?.package;
  return (
    <section className="panel review-panel">
      <div className="panel-heading"><div><p className="eyebrow">LANGGRAPH HUMAN-IN-THE-LOOP</p><h2>Review interrupt</h2></div><ClipboardCheck size={19} /></div>
      <div className="review-summary">
        <div><span>Status</span><strong>{review?.status || run.review_status || "loading"}</strong></div>
        <div><span>Readiness</span><strong>{packageData?.readiness_score ?? run.readiness_score}%</strong></div>
        <div><span>Fields</span><strong>{packageData?.profile?.field_count ?? "—"}</strong></div>
        <div><span>Requirements</span><strong>{packageData?.profile?.requirement_count ?? "—"}</strong></div>
      </div>
      {packageData?.summary && <p className="review-description">{packageData.summary}</p>}
      {!!packageData?.issues?.length && <div className="issue-list">{packageData.issues.slice(0, 8).map((issue, index) => <article key={`${issue.code}-${index}`}><ShieldAlert size={15} /><div><strong>{issue.code}</strong><p>{issue.message}</p></div><span>{issue.severity}</span></article>)}</div>}
      {review?.status === "awaiting_review" && <>
        <div className="decision-grid">
          <button className={decision === "approved" ? "selected approve" : ""} onClick={() => setDecision("approved")}><CheckCircle2 size={18} /><strong>Approve</strong><span>Accept profile and finish</span></button>
          <button className={decision === "changes_requested" ? "selected change" : ""} onClick={() => setDecision("changes_requested")}><RotateCcw size={18} /><strong>Request changes</strong><span>Return with reviewer notes</span></button>
          <button className={decision === "rejected" ? "selected reject" : ""} onClick={() => setDecision("rejected")}><XCircle size={18} /><strong>Reject</strong><span>Close as rejected</span></button>
        </div>
        <label>Reviewer comment<textarea rows="3" value={comment} onChange={(e) => setComment(e.target.value)} placeholder={decision === "approved" ? "Optional approval note" : "Required for this decision"} /></label>
        <label>Corrections JSON <span className="label-help">Allowed targets: field or requirement. Rejected decisions cannot contain corrections.</span><textarea className="code-input" rows="8" value={correctionsText} onChange={(e) => setCorrectionsText(e.target.value)} /></label>
        <details><summary>Correction example</summary><pre>{JSON.stringify([{ target_type: "field", target_key: "submission_deadline", patch: { effective_value: "2026-12-10", needs_review: false }, reason: "Confirmed from corrigendum" }], null, 2)}</pre></details>
        <button className="button primary submit-review" onClick={submit} disabled={busy}>{busy ? <LoaderCircle className="spin" size={16} /> : <ClipboardCheck size={16} />} Submit decision & resume graph</button>
      </>}
      {review?.status !== "awaiting_review" && review && <div className="decision-complete"><CheckCircle2 size={20} /><div><strong>Review completed: {review.status}</strong><p>{review.comment || "No reviewer comment."} · {review.correction_count} correction(s)</p></div></div>}
      {error && <p className="error-message">{error}</p>}
    </section>
  );
}
