import { useMemo, useState } from "react";
import { Braces, Search } from "lucide-react";

export function StateViewer({ run }) {
  const [query, setQuery] = useState("");
  const filtered = useMemo(() => Object.fromEntries(Object.entries(run || {}).filter(([key, value]) => !query || key.toLowerCase().includes(query.toLowerCase()) || JSON.stringify(value).toLowerCase().includes(query.toLowerCase()))), [query, run]);
  return (
    <section className="panel state-panel">
      <div className="panel-heading"><div><p className="eyebrow">CHECKPOINT VIEW</p><h2>Current public state</h2></div><Braces size={18} /></div>
      <label className="search-box"><Search size={15} /><input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Filter state keys or values" /></label>
      <pre>{JSON.stringify(filtered, null, 2)}</pre>
    </section>
  );
}
