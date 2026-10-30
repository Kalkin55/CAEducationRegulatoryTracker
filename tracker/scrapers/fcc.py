"""FCC Open Commission Meetings, via the Federal Register API.

fcc.gov refuses automated requests, but the FCC publishes a Sunshine Act
notice with each meeting's agenda in the Federal Register, whose API is meant
for this kind of use. The notice's official PDF (govinfo.gov) is attached as
the document, so its full text is searched for keywords."""

from __future__ import annotations

from urllib.parse import quote

from tracker.http import Fetcher
from tracker.models import DocLink, Item, Posting
from tracker.scrapers import register
from tracker.scrapers.base import Scraper
from tracker.scrapers.common import clean, parse_long_date

API = "https://www.federalregister.gov/api/v1/documents.json"
PARAMS = {
    "conditions[agencies][]": "federal-communications-commission",
    "conditions[term]": '"Open Commission Meeting"',
    "conditions[type][]": "NOTICE",
    "order": "newest",
    "per_page": "8",
}
FIELDS = ["title", "document_number", "html_url", "pdf_url", "publication_date", "abstract"]


@register
class FCC(Scraper):
    agency_id = "fcc"

    def fetch(self, fetcher: Fetcher) -> list[Posting]:
        url = API + "?" + "&".join(
            f"{quote(k, safe='[]')}={quote(v, safe='')}" for k, v in
            [*PARAMS.items(), *(("fields[]", f) for f in FIELDS)])
        return self.parse(fetcher.get(url).json())

    def parse(self, data: dict) -> list[Posting]:
        postings = []
        for r in data.get("results", []):
            title = clean(r["title"])
            if "open commission meeting" not in title.lower():
                continue
            # "Sunshine Act Meeting; Open Commission Meeting Thursday, October 29, 2026"
            meeting = title.split(";", 1)[-1].strip()
            items = [Item(title=clean(r["abstract"]), number="Summary")] if r.get("abstract") else []
            postings.append(Posting(
                external_key=r["document_number"],
                title=f"FCC {meeting}",
                meeting_date=parse_long_date(meeting),
                url=r["html_url"],
                items=items,
                documents=[DocLink(r["pdf_url"], "Federal Register notice (full agenda)")]
                if r.get("pdf_url") else [],
            ))
        return postings
