"""Apply database migrations (supabase/migrations/*.sql) that haven't run yet.

The first migration was applied by hand in the Supabase SQL editor; if the
schema already exists but nothing is recorded, it's marked as applied."""

from __future__ import annotations

import logging
from pathlib import Path

import psycopg

log = logging.getLogger(__name__)


def migrations_dir() -> Path | None:
    for base in (Path.cwd(), Path(__file__).resolve().parent.parent):
        d = base / "supabase" / "migrations"
        if d.is_dir():
            return d
    return None


def migrate(conn: psycopg.Connection, directory: Path | None = None) -> list[str]:
    """Returns the names of the migrations applied now."""
    directory = directory or migrations_dir()
    if directory is None:
        log.warning("supabase/migrations not found; skipping migrations")
        return []
    conn.execute("""create table if not exists public.schema_migrations (
                      name text primary key, applied_at timestamptz not null default now())""")
    conn.execute("alter table public.schema_migrations enable row level security")
    applied = {r[0] for r in conn.execute("select name from public.schema_migrations")}
    files = sorted(directory.glob("*.sql"))
    if not applied and files and conn.execute(
            "select to_regclass('public.agencies') is not null").fetchone()[0]:
        conn.execute("insert into public.schema_migrations (name) values (%s)", (files[0].name,))
        applied.add(files[0].name)
    done = []
    for f in files:
        if f.name in applied:
            continue
        log.info("applying migration %s", f.name)
        conn.execute(f.read_text())
        conn.execute("insert into public.schema_migrations (name) values (%s)", (f.name,))
        done.append(f.name)
    conn.commit()
    return done
