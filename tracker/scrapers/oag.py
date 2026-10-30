"""Attorney General: monthly legal-opinion report and active ballot initiatives."""

from __future__ import annotations

import datetime as dt
import re

from bs4 import BeautifulSoup, Tag

from tracker.http import Fetcher
from tracker.models import DocLink, Item, Posting
from tracker.scrapers import register
from tracker.scrapers.base import Scraper

OPINIONS_URL = "https://oag.ca.gov/opinions/monthly-report"
INITIATIVES_URL = "https://oag.ca.gov/initiatives/active-measures"


def _text(el: Tag | None) -> str:
    return re.sub(r"\s+", " ", el.get_text(" ", strip=True)).strip() if el else ""


def _us_date(s: str) -> dt.date | None:
    m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", s)
    return dt.date(int(m[3]), int(m[1]), int(m[2])) if m else None


def _long_date(s: str) -> dt.date | None:
    m = re.search(r"([A-Z][a-z]+)\s+(\d{1,2}),\s+(\d{4})", s)
    if not m:
        return None
    try:
        return dt.datetime.strptime(f"{m[1]} {m[2]} {m[3]}", "%B %d %Y").date()
    except ValueError:
        return None


def _short(s: str, n: int = 140) -> str:
    return s if len(s) <= n else s[: n - 1].rsplit(" ", 1)[0] + "…"


@register
class AGOpinions(Scraper):
    """One posting per opinion number. The report lists the same opinion in
    several tables (new, pending, issued); they're merged so that an opinion
    moving from pending to issued shows up as an update."""

    agency_id = "ag_opinions"

    def fetch(self, fetcher: Fetcher) -> list[Posting]:
        return self.parse(fetcher.get(OPINIONS_URL).content)

    def parse(self, html: bytes) -> list[Posting]:
        soup = BeautifulSoup(html, "html.parser")
        ops: dict[str, dict] = {}
        for table in soup.find_all("table"):
            headers = [_text(th).lower() for th in table.find_all("th")]
            if not headers or not headers[0].startswith("opinion no"):
                continue
            for tr in table.find_all("tr"):
                cells = tr.find_all("td")
                if len(cells) < 3:
                    continue
                row = {h: c for h, c in zip(headers, cells)}
                number = _text(cells[0])
                if not re.fullmatch(r"\d{2}-\d{3,4}", number):
                    continue
                op = ops.setdefault(number, {"question": "", "conclusion": "", "status": None,
                                             "date": None, "pdf": None, "assigned": ""})
                question = _text(row.get("question(s) presented"))
                # The issued-opinion tables have the fullest wording; prefer the longest.
                if len(question) > len(op["question"]):
                    op["question"] = question
                link = cells[0].find("a", href=True)
                if link and link["href"].lower().endswith(".pdf"):
                    op["pdf"] = self.absolute(OPINIONS_URL, link["href"])
                if "conclusion(s)" in row:
                    op["conclusion"] = _text(row["conclusion(s)"])
                    issued = _text(row.get("issued"))
                    op["status"] = f"Issued {issued}".strip()
                    op["date"] = _us_date(issued) or op["date"]
                elif "status" in row:
                    status = _text(row["status"])
                    op["status"] = status
                    op["date"] = _us_date(status) or op["date"]
                if "assigned to" in row:
                    op["assigned"] = re.sub(r"\s*\d{1,2}/\d{1,2}/\d{4}", "", _text(row["assigned to"]))

        postings = []
        for number, op in ops.items():
            status = op["status"] or "Pending"
            items = [Item(title=op["question"], number="Question")]
            if op["conclusion"]:
                items.append(Item(title=op["conclusion"], number="Conclusion"))
            # Who it's assigned to only matters while pending, and it's only listed
            # some months, so leaving it off issued opinions avoids false "updated" flags.
            pending = op["status"] is None
            items.append(Item(title=status + (f" (assigned to {op['assigned']})"
                                              if pending and op["assigned"] else ""),
                              number="Status"))
            postings.append(Posting(
                external_key=number,
                kind="opinion",
                title=f"Opinion {number} ({status}): {_short(op['question'])}",
                meeting_date=op["date"],
                url=op["pdf"] or OPINIONS_URL,
                items=items,
                documents=[DocLink(op["pdf"], f"Opinion {number} (PDF)")] if op["pdf"] else [],
            ))
        return postings


@register
class AGInitiatives(Scraper):
    """One posting per initiative. Amended versions (26-0006A2) update the
    original tracking number's posting instead of creating a new one."""

    agency_id = "ag_initiatives"

    def fetch(self, fetcher: Fetcher) -> list[Posting]:
        return self.parse(fetcher.get(INITIATIVES_URL).content)

    def parse(self, html: bytes) -> list[Posting]:
        soup = BeautifulSoup(html, "html.parser")
        postings: dict[str, Posting] = {}
        for tr in soup.select("table tr"):
            cells = tr.find_all("td")
            if len(cells) < 2:
                continue
            tracking = _text(cells[0])
            m = re.match(r"(\d{2}-\d{4})", tracking)
            if not m:
                continue
            body = cells[1]
            lines = [ln.strip() for ln in body.get_text("\n", strip=True).split("\n") if ln.strip()]
            joined = " ".join(lines)
            title = lines[0] if lines else tracking
            proponents = re.search(r"Proponent\(s\):\s*(.+?)(?:\s+(?:Submitted|Title and Summary|Comment period|View Comments|Fiscal)|$)",
                                   joined)
            status_m = re.search(r"(Submitted for Title and Summary on \S+ \d{1,2}, \d{4}"
                                 r"|Title and Summary Issued on \S+ \d{1,2}, \d{4})", joined)
            status = status_m[1] if status_m else ""
            docs = []
            text_link = cells[0].find("a", href=True)
            if text_link:
                docs.append(DocLink(self.absolute(INITIATIVES_URL, text_link["href"]),
                                    f"Initiative text ({tracking})"))
            for a in body.find_all("a", href=True):
                if a["href"].lower().endswith(".pdf"):
                    label = _text(a) or "Document"
                    if label.startswith("Title and Summary"):
                        label = "Official title and summary"
                    docs.append(DocLink(self.absolute(INITIATIVES_URL, a["href"]), label))
            items = [Item(title=status or "Status not listed", number="Status")]
            if proponents:
                items.append(Item(title=proponents[1].strip(), number="Proponents"))
            postings[m[1]] = Posting(
                external_key=m[1],
                kind="initiative",
                title=f"{tracking}: {title}",
                meeting_date=_long_date(status),
                url=docs[0].url if docs else INITIATIVES_URL,
                items=items,
                documents=docs,
            )
        return list(postings.values())
