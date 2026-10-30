"""Tests run against a real Postgres: the migrations are applied once to a
template database and each test gets a fresh copy.

Set TEST_ADMIN_DATABASE_URL to a server where you can create databases, e.g.
postgresql://postgres@localhost:5432/postgres
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import psycopg
import pytest

ROOT = Path(__file__).resolve().parent.parent
ADMIN_URL = os.environ.get("TEST_ADMIN_DATABASE_URL")
TEMPLATE = "tracker_template"


def _with_db(url: str, dbname: str) -> str:
    return psycopg.conninfo.make_conninfo(url, dbname=dbname)


@pytest.fixture(scope="session")
def template_db():
    if not ADMIN_URL:
        pytest.skip("TEST_ADMIN_DATABASE_URL not set")
    with psycopg.connect(ADMIN_URL, autocommit=True) as admin:
        admin.execute(f"drop database if exists {TEMPLATE}")
        admin.execute(f"create database {TEMPLATE}")
    with psycopg.connect(_with_db(ADMIN_URL, TEMPLATE), autocommit=True) as conn:
        conn.execute((ROOT / "tests/sql/supabase_stub.sql").read_text())
        for f in sorted((ROOT / "supabase/migrations").glob("*.sql")):
            conn.execute(f.read_text())
    return TEMPLATE


@pytest.fixture
def conn(template_db):
    name = f"t_{uuid.uuid4().hex[:12]}"
    with psycopg.connect(ADMIN_URL, autocommit=True) as admin:
        admin.execute(f"create database {name} template {template_db}")
    c = psycopg.connect(_with_db(ADMIN_URL, name))
    from tracker.pipeline import sync_agencies
    sync_agencies(c)
    c.commit()
    yield c
    c.close()
    with psycopg.connect(ADMIN_URL, autocommit=True) as admin:
        admin.execute(f"drop database {name} with (force)")


class FakeResponse:
    def __init__(self, content: bytes, content_type: str):
        self.content = content
        self.headers = {"content-type": content_type}


class FakeFetcher:
    """Serves canned responses by URL; anything else is a fetch error."""

    def __init__(self, pages: dict[str, tuple[bytes | str, str]] | None = None):
        self.pages = dict(pages or {})
        self.requests: list[str] = []

    def get(self, url: str):
        from tracker.http import FetchError

        self.requests.append(url)
        if url not in self.pages:
            raise FetchError(f"HTTP 404 for {url}")
        body, ctype = self.pages[url]
        return FakeResponse(body.encode() if isinstance(body, str) else body, ctype)


@pytest.fixture
def fetcher():
    return FakeFetcher()
