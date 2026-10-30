"""California Collaborative for Educational Excellence governing board.

The meetings page itself sits behind a Cloudflare challenge, but the site's
public WordPress API serves the same page content, and the linked PDFs
download normally."""

from __future__ import annotations

import datetime as dt
from urllib.parse import parse_qs, urlsplit

from bs4 import BeautifulSoup

from tracker.http import Fetcher
from tracker.models import DocLink, Posting
from tracker.scrapers import register
from tracker.scrapers.base import Scraper
from tracker.scrapers.common import is_document, parse_long_date, text

PAGE_URL = "https://ccee-ca.org/governing-board/meetings/"
API_URL = "https://ccee-ca.org/wp-json/wp/v2/pages/31303?_fields=id,link,modified,title,content"
# Older meetings stay on the page for years; only track roughly the last year.
HISTORY_DAYS = 400


@register
class CCEE(Scraper):
    agency_id = "ccee"

    def fetch(self, fetcher: Fetcher) -> list[Posting]:
        page = fetcher.get(API_URL).json()
        return self.parse(page["content"]["rendered"])

    def parse(self, html: str, today: dt.date | None = None) -> list[Posting]:
        today = today or dt.date.today()
        soup = BeautifulSoup(html, "html.parser")
        postings: dict[str, Posting] = {}
        for tr in soup.select("table tr"):
            cells = tr.find_all("td")
            if not cells:
                continue
            label = text(cells[0])
            date = parse_long_date(label)
            if not date or date < today - dt.timedelta(days=HISTORY_DAYS):
                continue
            docs = []
            for a in tr.find_all("a", href=True):
                url = _unwrap(a["href"])
                if is_document(url):
                    docs.append(DocLink(url, text(a) or None))
            if not docs:
                continue  # scheduled, but nothing posted yet
            postings.setdefault(date.isoformat(), Posting(
                external_key=date.isoformat(),
                title=f"CCEE Governing Board Meeting - {label}",
                meeting_date=date,
                url=docs[0].url,
                documents=docs,
            ))
        return list(postings.values())


def _unwrap(href: str) -> str:
    """Some links were pasted from Outlook and wrapped in a safelinks redirect."""
    parts = urlsplit(href)
    if parts.netloc.endswith("safelinks.protection.outlook.com"):
        return parse_qs(parts.query).get("url", [href])[0]
    return href
