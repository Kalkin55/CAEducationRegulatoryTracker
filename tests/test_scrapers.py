"""Scrapers against saved copies of the agency pages (tests/fixtures/<agency>/).
When a site is redesigned, re-save the page and update these expectations."""

import datetime as dt
import json
from pathlib import Path

from tests.conftest import FakeFetcher
from tracker.scrapers.ctc import BASE, CTC
from tracker.scrapers.oag import AGInitiatives, AGOpinions

FIX = Path(__file__).parent / "fixtures"


def test_ag_opinions_merges_tables_per_opinion():
    postings = {p.external_key: p for p in AGOpinions().parse((FIX / "ag_opinions/monthly-report.html").read_bytes())}
    assert len(postings) == 15
    issued = postings["26-901"]
    assert issued.kind == "opinion"
    assert issued.meeting_date == dt.date(2026, 10, 7)
    assert issued.title.startswith("Opinion 26-901 (Issued 10/07/2026): DANIEL BOOKMAN")
    assert [i.number for i in issued.items] == ["Question", "Conclusion", "Status"]
    assert issued.items[2].title == "Issued 10/07/2026"  # no month-specific "assigned to"
    assert [d.url for d in issued.documents] == ["https://oag.ca.gov/system/files/opinions/pdfs/26-901.pdf"]

    withdrawn = postings["26-203"]
    assert withdrawn.items[-1].title == "Withdrawn on 09/01/2026" and not withdrawn.documents

    pending = postings["26-602"]
    assert pending.items[-1].title == "Pending (assigned to Thomas)"
    assert pending.meeting_date is None


def test_ag_initiatives():
    postings = AGInitiatives().parse((FIX / "ag_initiatives/active-measures.html").read_bytes())
    assert len(postings) == 46
    by_key = {p.external_key: p for p in postings}
    amended = by_key["26-0006"]  # 26-0006A2 updates the original posting
    assert amended.title == "26-0006A2: “Approval Voting Act”"
    assert amended.meeting_date == dt.date(2026, 9, 11)
    assert [i.title for i in amended.items] == [
        "Submitted for Title and Summary on September 11, 2026", "Amanda Mahlendorf"]

    food = by_key["26-0005"]
    assert food.meeting_date == dt.date(2026, 9, 25)
    assert [d.label for d in food.documents] == [
        "Initiative text (26-0005)", "Official title and summary", "Fiscal Impact Estimate Report"]


def test_ctc_meeting_with_items_and_documents():
    meetings = json.loads((FIX / "ctc/meetings.json").read_text())
    fetcher = FakeFetcher({f"{BASE}/Details/381": ((FIX / "ctc/details-381.html").read_bytes(), "text/html")})
    fetcher.post = lambda url, **kw: type("R", (), {"json": lambda self: meetings})()
    [p] = CTC().fetch(fetcher)
    assert p.external_key == "381"
    assert p.meeting_date == dt.date(2026, 10, 29)
    assert p.title == "Committee on Accreditation Meeting - October 29, 2026 (Committee on Accreditation (COA))"
    assert len(p.items) == 18
    item12 = p.items[11]
    assert (item12.number, item12.title) == ("12", "Report of the Accreditation Site Visit Team to Summit Prep Charter HS")
    assert p.items[-1].number is None and p.items[-1].title == "Adjournment"
    assert len(p.documents) == 11
    insert = next(d for d in p.documents if "INSERT" in (d.label or ""))
    assert insert.url == f"{BASE}/Document/Download/10915" and p.items[insert.item_index].number == "5"
