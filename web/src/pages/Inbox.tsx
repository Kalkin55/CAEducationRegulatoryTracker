import { useState } from "react";
import { supabase } from "../supabase";
import type { Agency, PostingRow } from "../types";
import { StatusBadge, fmtDate, must, useLoad } from "../util";

type View = "needs-review" | "keyword-hits" | "all";

export default function Inbox({ agencyFilter }: { agencyFilter?: string }) {
  const [view, setView] = useState<View>("needs-review");
  const [agency, setAgency] = useState(agencyFilter ?? "");
  const [busy, setBusy] = useState<number | null>(null);

  const agencies = useLoad(
    async () => must(await supabase.from("agencies").select("*").order("name")) as Agency[],
    [],
  );
  const postings = useLoad(async () => {
    let q = supabase.from("posting_status").select("*");
    if (view === "needs-review") q = q.in("status", ["new", "updated"]);
    if (view === "keyword-hits") q = q.gt("match_count", 0);
    if (agency) q = q.eq("agency_id", agency);
    q = q.order("meeting_date", { ascending: false, nullsFirst: true })
         .order("first_seen_at", { ascending: false }).limit(view === "needs-review" ? 500 : 200);
    return must(await q) as PostingRow[];
  }, [view, agency]);

  async function markReviewed(id: number) {
    setBusy(id);
    const { error } = await supabase.from("reviews").insert({ posting_id: id });
    setBusy(null);
    if (error) alert(error.message);
    else postings.reload();
  }

  const groups = new Map<string, PostingRow[]>();
  for (const p of postings.data ?? []) {
    const list = groups.get(p.agency_name) ?? [];
    list.push(p);
    groups.set(p.agency_name, list);
  }
  const failing = (agencies.data ?? []).filter((a) => a.consecutive_failures >= 3);

  return (
    <>
      <div className="toolbar">
        <div className="segmented">
          {([["needs-review", "Needs review"], ["keyword-hits", "Keyword hits"], ["all", "All"]] as const)
            .map(([v, label]) => (
              <button key={v} className={view === v ? "on" : ""} onClick={() => setView(v)}>{label}</button>
            ))}
        </div>
        <select value={agency} onChange={(e) => setAgency(e.target.value)}>
          <option value="">All agencies</option>
          {(agencies.data ?? []).map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
        </select>
      </div>

      {failing.length > 0 && (
        <p className="warning">
          Not updating, so check these by hand: {failing.map((a) => a.short_name).join(", ")}.{" "}
          <a href="#/agencies">Details</a>
        </p>
      )}
      {postings.error && <p className="error">{postings.error}</p>}
      {postings.data && postings.data.length === 0 && (
        <p className="empty">{view === "needs-review" ? "Nothing to review. You're caught up." : "No postings."}</p>
      )}

      {[...groups].map(([agencyName, rows]) => (
        <section key={agencyName} className="group">
          <h2>{agencyName} <span className="count">{rows.length}</span></h2>
          <ul className="postings">
            {rows.map((p) => (
              <li key={p.id}>
                <div className="row-main">
                  <StatusBadge status={p.status} />
                  <a href={`#/posting/${p.id}`} className="title">{p.title}</a>
                  {p.meeting_date && <span className="muted">{fmtDate(p.meeting_date)}</span>}
                </div>
                <div className="row-meta">
                  {p.matched_keywords.map((k) => <span key={k} className="badge kw">{k}</span>)}
                  {p.status === "reviewed" && (
                    <span className="muted">
                      Reviewed by {p.last_reviewed_by_name || p.last_reviewed_by_email} {fmtDate(p.last_reviewed_at)}
                    </span>
                  )}
                  {p.url && <a href={p.url} target="_blank" rel="noreferrer">Source ↗</a>}
                  {(p.status === "new" || p.status === "updated") && (
                    <button className="small" disabled={busy === p.id} onClick={() => markReviewed(p.id)}>
                      Mark reviewed
                    </button>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </>
  );
}
