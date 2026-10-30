import { useState } from "react";
import { supabase } from "../supabase";
import type { Agency, Keyword } from "../types";
import { must, useLoad } from "../util";

const TYPE_HELP: Record<Keyword["match_type"], string> = {
  word: "Whole word, plurals included (charter → charters)",
  phrase: "Exact words in order",
  regex: "Regular expression (advanced)",
};

export default function Keywords() {
  const [term, setTerm] = useState("");
  const [matchType, setMatchType] = useState<Keyword["match_type"]>("word");
  const [agencyId, setAgencyId] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const { data, error, reload } = useLoad(async () => {
    const [kw, ag, m] = await Promise.all([
      supabase.from("keywords").select("*").order("term"),
      supabase.from("agencies").select("id, name, short_name").order("name"),
      supabase.from("matches").select("keyword_id, posting_id"),
    ]);
    const postings = new Map<number, Set<number>>();
    for (const r of must(m) as { keyword_id: number; posting_id: number }[]) {
      if (!postings.has(r.keyword_id)) postings.set(r.keyword_id, new Set());
      postings.get(r.keyword_id)!.add(r.posting_id);
    }
    return { keywords: must(kw) as Keyword[], agencies: must(ag) as Agency[], postings };
  }, []);

  async function add(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setErr(null);
    // Saving also searches every stored agenda, so this can take a few seconds.
    const { error } = await supabase.from("keywords")
      .insert({ term: term.trim(), match_type: matchType, agency_id: agencyId || null });
    setSaving(false);
    if (error) setErr(error.message);
    else { setTerm(""); reload(); }
  }
  async function update(k: Keyword, patch: Partial<Keyword>) {
    const { error } = await supabase.from("keywords").update(patch).eq("id", k.id);
    if (error) alert(error.message); else reload();
  }
  async function remove(k: Keyword) {
    if (!confirm(`Delete keyword "${k.term}"?`)) return;
    const { error } = await supabase.from("keywords").delete().eq("id", k.id);
    if (error) alert(error.message); else reload();
  }

  if (error) return <p className="error">{error}</p>;
  if (!data) return null;

  return (
    <>
      <h1>Keywords</h1>
      <p className="muted">
        Keywords are matched against agenda titles, item text and linked documents. New keywords also search
        everything already collected.
      </p>
      <form className="keyword-form" onSubmit={add}>
        <input placeholder="e.g. charter, Prop 39, Acme Academy" value={term}
               onChange={(e) => setTerm(e.target.value)} required />
        <select value={matchType} onChange={(e) => setMatchType(e.target.value as Keyword["match_type"])}
                title={TYPE_HELP[matchType]}>
          <option value="word">Word</option>
          <option value="phrase">Exact phrase</option>
          <option value="regex">Regex</option>
        </select>
        <select value={agencyId} onChange={(e) => setAgencyId(e.target.value)}>
          <option value="">All agencies</option>
          {data.agencies.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
        </select>
        <button disabled={saving}>{saving ? "Searching…" : "Add keyword"}</button>
      </form>
      <p className="muted small-text">{TYPE_HELP[matchType]}</p>
      {err && <p className="error">{err}</p>}

      <table>
        <thead><tr><th>Keyword</th><th>Type</th><th>Agencies</th><th>Postings matched</th><th>Active</th><th /></tr></thead>
        <tbody>
          {data.keywords.map((k) => (
            <tr key={k.id} className={k.active ? "" : "inactive"}>
              <td><code>{k.term}</code></td>
              <td>{k.match_type}</td>
              <td>
                <select value={k.agency_id ?? ""} onChange={(e) => update(k, { agency_id: e.target.value || null })}>
                  <option value="">All agencies</option>
                  {data.agencies.map((a) => <option key={a.id} value={a.id}>{a.short_name}</option>)}
                </select>
              </td>
              <td>{data.postings.get(k.id)?.size ?? 0}</td>
              <td><input type="checkbox" checked={k.active} onChange={(e) => update(k, { active: e.target.checked })} /></td>
              <td><button className="link danger" onClick={() => remove(k)}>Delete</button></td>
            </tr>
          ))}
        </tbody>
      </table>
      {data.keywords.length === 0 && <p className="empty">No keywords yet.</p>}
    </>
  );
}
