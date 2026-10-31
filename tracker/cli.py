"""Command line: python -m tracker <command>."""

from __future__ import annotations

import argparse
import logging
import os
import sys

import psycopg

from tracker import notify, pipeline
from tracker.agencies import AGENCIES
from tracker.http import Fetcher
from tracker.scrapers import get_scraper


def connect() -> psycopg.Connection:
    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL is not set (use the Supabase session-pooler connection string)")
    return psycopg.connect(url)


class _NoCommit:
    """Connection proxy for --dry-run: everything runs, nothing is kept."""

    def __init__(self, conn):
        self._conn = conn

    def execute(self, *a, **kw):
        return self._conn.execute(*a, **kw)

    def commit(self):
        pass

    def rollback(self):
        self._conn.rollback()


def cmd_run(args) -> int:
    fetcher = Fetcher()
    try:
        skip = {a.strip() for a in args.exclude.split(",") if a.strip()}
        wanted = args.agency + [a.strip() for a in args.agencies.split(",") if a.strip()]
        unknown = [a for a in wanted + list(skip) if a not in {x.id for x in AGENCIES}]
        if unknown:
            sys.exit(f"unknown agency id(s): {', '.join(unknown)}")
        selected = [a for a in (wanted or [x.id for x in AGENCIES]) if a not in skip]
        if args.no_db:
            return preview(fetcher, selected)
        with connect() as conn:
            db = _NoCommit(conn) if args.dry_run else conn
            results = pipeline.run(db, fetcher, selected)
            for r in results:
                status = "skipped" if r.skipped else ("ok" if r.ok else "FAILED")
                print(f"{r.agency_id:15} {status:8} new={len(r.new)} updated={len(r.updated)} "
                      f"unchanged={r.unchanged} already_posted={r.baseline} {r.error or ''}")
            if args.dry_run:
                print_matches(conn, [i for r in results for i in r.new + r.updated])
                conn.rollback()
                print("\n(dry run: nothing was saved)")
                return 0
            write_step_summary(results)
            notify.send_health_alerts(results)
            if not args.no_email:
                notify.send_user_alerts(conn, "immediate")
        failed = [r for r in results if not r.ok and not r.skipped]
        return 1 if failed and len(failed) == len([r for r in results if not r.skipped]) else 0
    finally:
        fetcher.close()


def write_step_summary(results) -> None:
    """On GitHub Actions, show a per-agency table on the run's page."""
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    from tracker.agencies import BY_ID

    lines = ["| Agency | Result | New | Updated | Unchanged | First run (already posted) |",
             "|---|---|---|---|---|---|"]
    for r in results:
        result = ("Not automated yet" if r.skipped else "OK" if r.ok
                  else f"Failed: {(r.error or '').replace('|', '/')[:150]}")
        lines.append(f"| {BY_ID[r.agency_id].name} | {result} | {len(r.new)} | {len(r.updated)} "
                     f"| {r.unchanged} | {r.baseline} |")
    with open(path, "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def preview(fetcher: Fetcher, agency_ids: list[str]) -> int:
    for agency_id in agency_ids or [a.id for a in AGENCIES]:
        scraper = get_scraper(agency_id)
        if not scraper:
            print(f"== {agency_id}: scraper not built yet")
            continue
        postings = scraper.fetch(fetcher)
        print(f"== {agency_id}: {len(postings)} postings")
        for p in postings:
            print(f"  [{p.kind}] {p.meeting_date or '----------'} {p.title}  <{p.url}>")
            for i in p.items:
                print(f"      {i.number or '-'}  {i.title[:110]}")
            for d in p.documents:
                print(f"      doc: {d.label or ''} <{d.url}>")
    return 0


def print_matches(conn, posting_ids: list[int]) -> None:
    if not posting_ids:
        return
    rows = conn.execute(
        """select a.short_name, p.title, k.term, m.source, m.snippet
           from matches m join postings p on p.id = m.posting_id
           join agencies a on a.id = p.agency_id join keywords k on k.id = m.keyword_id
           where m.posting_id = any(%s) order by a.short_name, p.title""",
        (posting_ids,),
    ).fetchall()
    print(f"\nKeyword matches ({len(rows)}):")
    for agency, title, term, source, snippet in rows:
        print(f"  {agency} | {title[:60]} | {term} in {source}: {snippet[:140]}")


def cmd_digest(args) -> int:
    with connect() as conn:
        print(f"sent {notify.send_user_alerts(conn, 'daily')} digest email(s)")
    return 0


def cmd_rematch(args) -> int:
    with connect() as conn:
        conn.execute("select rematch(null, null)")
        conn.commit()
    print("rematched all postings")
    return 0


def cmd_sync(args) -> int:
    with connect() as conn:
        pipeline.sync_agencies(conn)
        conn.commit()
    print(f"synced {len(AGENCIES)} agencies")
    return 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("pdfminer").setLevel(logging.ERROR)  # noisy font warnings
    logging.getLogger("httpx").setLevel(logging.WARNING)
    ap = argparse.ArgumentParser(prog="tracker")
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="scrape agencies and store changes")
    r.add_argument("--agency", action="append", default=[], choices=[a.id for a in AGENCIES],
                   help="limit to one agency (repeatable)")
    r.add_argument("--agencies", default="",
                   help="comma-separated agency ids to check (same as repeating --agency)")
    r.add_argument("--exclude", default="",
                   help="comma-separated agency ids to skip (e.g. ones checked from another machine)")
    r.add_argument("--dry-run", action="store_true",
                   help="run against the database but roll everything back")
    r.add_argument("--no-db", action="store_true",
                   help="just print what the scrapers find; no database needed")
    r.add_argument("--no-email", action="store_true", help="skip immediate email alerts")
    r.set_defaults(func=cmd_run)

    sub.add_parser("digest", help="send the daily digest emails").set_defaults(func=cmd_digest)
    sub.add_parser("rematch", help="re-run all keywords over stored text").set_defaults(func=cmd_rematch)
    sub.add_parser("sync-agencies", help="write the agency list to the database").set_defaults(func=cmd_sync)

    args = ap.parse_args(argv)
    return args.func(args)
