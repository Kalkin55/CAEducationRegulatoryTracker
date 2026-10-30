import { supabase } from "../supabase";
import type { Agency } from "../types";
import { fmtDateTime, must, useLoad } from "../util";

export default function Agencies() {
  const { data, error } = useLoad(async () => {
    const agencies = must(await supabase.from("agencies").select("*").order("name")) as Agency[];
    const open = must(await supabase.from("posting_status").select("agency_id")
      .in("status", ["new", "updated"])) as { agency_id: string }[];
    const counts = new Map<string, number>();
    for (const r of open) counts.set(r.agency_id, (counts.get(r.agency_id) ?? 0) + 1);
    return { agencies, counts };
  }, []);

  if (error) return <p className="error">{error}</p>;
  if (!data) return null;

  return (
    <table className="agencies">
      <thead>
        <tr><th>Agency</th><th>To review</th><th>Last checked</th><th>Last successful</th><th>Health</th></tr>
      </thead>
      <tbody>
        {data.agencies.map((a) => (
          <tr key={a.id}>
            <td>
              <a href={`#/agency/${a.id}`}>{a.name}</a>{" "}
              <a href={a.url} target="_blank" rel="noreferrer" className="muted">site ↗</a>
            </td>
            <td>{data.counts.get(a.id) ?? 0}</td>
            <td>{fmtDateTime(a.last_checked_at)}</td>
            <td>{fmtDateTime(a.last_success_at)}</td>
            <td>
              {!a.scraper_ready ? <span className="badge status-baseline">Not automated yet: check by hand</span>
                : a.consecutive_failures >= 3 ? <span className="badge bad" title={a.last_error ?? ""}>Failing: check by hand</span>
                : a.consecutive_failures > 0 ? <span className="badge warn" title={a.last_error ?? ""}>Last check failed</span>
                : a.last_success_at ? <span className="badge ok">OK</span>
                : <span className="muted">Waiting for first run</span>}
              {a.last_error && a.consecutive_failures > 0 && <div className="muted small-text">{a.last_error}</div>}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
