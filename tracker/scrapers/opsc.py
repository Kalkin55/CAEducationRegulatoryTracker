"""Office of Public School Construction / State Allocation Board meetings (dgs.ca.gov).

The page lists upcoming meetings as a heading paragraph ("State Allocation
Board Meeting - Wednesday, October 28, 2026 at ...") followed by a list of
links. Zoom and webcast links are skipped; documents are kept. Meetings are
included before their documents are posted, so new webinars are flagged early."""

from __future__ import annotations

import datetime as dt
import re

from bs4 import BeautifulSoup

from tracker.http import Fetcher
from tracker.models import DocLink, Posting
from tracker.scrapers import register
from tracker.scrapers.base import Scraper
from tracker.scrapers.common import is_document, parse_long_date, text

LISTING = "https://www.dgs.ca.gov/OPSC/Meetings"
HEADING = re.compile(r"^(?P<title>.+?)\s*[-–]\s*(?P<when>(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),.+)$")


@register
class OPSC(Scraper):
    agency_id = "opsc"

    def fetch(self, fetcher: Fetcher) -> list[Posting]:
        return self.parse(fetcher.get(LISTING).content)

    def parse(self, html: bytes, today: dt.date | None = None) -> list[Posting]:
        soup = BeautifulSoup(html, "html.parser")
        main = soup.find("main") or soup
        postings: list[Posting] = []
        for p in main.find_all("p"):
            m = HEADING.match(text(p))
            if not m:
                continue
            if p.find_parent(class_=re.compile("accordion")):
                continue  # the OPSC Online training workshops
            ul = p.find_next_sibling()
            if not ul or ul.name != "ul":
                continue
            date = parse_long_date(m["when"], today)
            docs = [DocLink(self.absolute(LISTING, a["href"]), text(a) or None)
                    for a in ul.find_all("a", href=True) if is_document(a["href"])]
            title = f"{m['title']} - {date.strftime('%B %-d, %Y') if date else m['when']}"
            postings.append(Posting(
                external_key=f"{date.isoformat() if date else m['when']}|{m['title'].lower()}",
                title=title,
                meeting_date=date,
                url=docs[0].url if docs else LISTING,
                documents=docs,
            ))
        return postings
