import { useState } from "react";
import { supabase } from "../supabase";
import type { Doc, Item, Keyword, Match, PostingRow, Review } from "../types";
import { Highlight, StatusBadge, fmtDate, fmtDateTime, keywordRegex, must, useLoad } from "../util";

export default function PostingPage({ id, userId }: { id: number; userId: string }) {
  const [note, setNote] = useState("");
  const [onlyHits, setOnlyHits] = useState(false);

  const { data, error, reload } = useLoad(async () => {
    const [posting, items, docs, matches, reviews, keywords] = await Promise.all([
      supabase.from("posting_status").select("*").eq("id", id).single(),
      supabase.from("items").select("*").eq("posting_id", id).order("position"),
      supabase.from("documents").select("id, item_position, url, label, fetch_error, text")
        .eq("posting_id", id).order("id"),
      supabase.from("matches").select("*").eq("posting_id", id),
      supabase.from("reviews").select("*, profiles(email, display_name)").eq("posting_id", id)
        .order("reviewed_at", { ascending: false }),
      supabase.from("keywords").select("*"),
    ]);
    return {
      posting: must(posting) as PostingRow,
      items: must(items) as Item[],
      docs: must(docs) as Doc[],
      matches: must(matches) as Match[],
      reviews: must(reviews) as Review[],
      keywords: must(keywords) as Keyword[],
    };
  }, [id]);

  if (error) return <p className="error">{error}</p>;
  if (!data) return null;
  const { posting: p, items, docs, matches, reviews, keywords } = data;

  const kwById = new Map(keywords.map((k) => [k.id, k]));
  const patterns = [...new Set(matches.map((m) => m.keyword_id))]
    .map((k) => kwById.get(k)).filter(Boolean).map((k) => keywordRegex(k!));
  const matchedItems = new Set(matches.filter((m) => m.item_id).map((m) => m.item_id));
  const docsByItem = new Map<number, Doc[]>();
  for (const d of docs) {
    if (d.item_position == null) continue;
    docsByItem.set(d.item_position, [...(docsByItem.get(d.item_position) ?? []), d]);
  }
  const generalDocs = docs.filter((d) => d.item_position == null);

  async function review() {
    const { error } = await supabase.from("reviews").insert({ posting_id: id, note: note || null });
    if (error) alert(error.message);
    else { setNote(""); reload(); }
  }
  async function undo(reviewId: number) {
    const { error } = await supabase.from("reviews").delete().eq("id", reviewId);
    if (error) alert(error.message);
    else reload();
  }

  return (
    <article className="posting">
      <p><a href={`#/agency/${p.agency_id}`}>← {p.agency_name}</a></p>
      <h1><Highlight text={p.title} patterns={patterns} /></h1>
      <p className="row-meta">
        <StatusBadge status={p.status} />
        {p.meeting_date && <span>{p.kind === "meeting" ? "Meeting" : "Dated"} {fmtDate(p.meeting_date)}</span>}
        <span className="muted">First seen {fmtDateTime(p.first_seen_at)}</span>
        {p.last_changed_at !== p.first_seen_at && <span className="muted">Changed {fmtDateTime(p.last_changed_at)}</span>}
        {p.url && <a href={p.url} target="_blank" rel="noreferrer">Open on agency site ↗</a>}
      </p>

      <section className="review-box">
        <textarea placeholder="Optional note (e.g. 'Item 5 is the Acme appeal, flagged for legal')"
                  value={note} onChange={(e) => setNote(e.target.value)} />
        <button onClick={review}>{p.status === "reviewed" ? "Add note / review again" : "Mark reviewed"}</button>
        {reviews.length > 0 && (
          <ul className="reviews">
            {reviews.map((r) => (
              <li key={r.id}>
                <b>{r.profiles?.display_name || r.profiles?.email}</b> reviewed {fmtDateTime(r.reviewed_at)}
                {r.note && <>: {r.note}</>}
                {r.user_id === userId && <button className="link" onClick={() => undo(r.id)}>undo</button>}
              </li>
            ))}
          </ul>
        )}
      </section>

      {matches.length > 0 && (
        <section>
          <h2>Keyword matches</h2>
          <ul className="matches">
            {matches.map((m) => {
              const doc = docs.find((d) => d.id === m.document_id);
              const item = items.find((i) => i.id === m.item_id);
              return (
                <li key={m.id}>
                  <span className="badge kw">{kwById.get(m.keyword_id)?.term}</span>{" "}
                  <span className="muted">
                    {m.source === "title" && "in title"}
                    {item && <>in item <a href={`#item-${item.id}`} onClick={(e) => { e.preventDefault(); document.getElementById(`item-${item.id}`)?.scrollIntoView(); }}>{item.number ?? item.position + 1}</a></>}
                    {doc && <>in <a href={doc.url} target="_blank" rel="noreferrer">{doc.label || "document"}</a></>}
                    {m.hit_count > 1 && ` (${m.hit_count}×)`}
                  </span>
                  <blockquote><Highlight text={m.snippet} patterns={patterns} /></blockquote>
                </li>
              );
            })}
          </ul>
        </section>
      )}

      {items.length > 0 && (
        <section>
          <h2>Agenda items</h2>
          <label className="muted inline">
            <input type="checkbox" checked={onlyHits} onChange={(e) => setOnlyHits(e.target.checked)} />{" "}
            Only items with keyword hits
          </label>
          <ol className="items">
            {items.filter((i) => !onlyHits || matchedItems.has(i.id)).map((i) => (
              <li key={i.id} id={`item-${i.id}`} className={matchedItems.has(i.id) ? "hit" : ""}>
                <div><b>{i.number}</b> <Highlight text={i.title} patterns={patterns} /></div>
                {i.description && <p><Highlight text={i.description} patterns={patterns} /></p>}
                {(docsByItem.get(i.position) ?? []).map((d) => <DocLink key={d.id} d={d} />)}
              </li>
            ))}
          </ol>
        </section>
      )}

      {generalDocs.length > 0 && (
        <section>
          <h2>Documents</h2>
          <ul>{generalDocs.map((d) => <li key={d.id}><DocLink d={d} /></li>)}</ul>
        </section>
      )}
    </article>
  );
}

function DocLink({ d }: { d: Doc }) {
  return (
    <div className="doc">
      <a href={d.url} target="_blank" rel="noreferrer">{d.label || d.url.split("/").pop()}</a>
      {d.fetch_error && <span className="muted" title={d.fetch_error}> (text not searchable: {d.fetch_error})</span>}
    </div>
  );
}
