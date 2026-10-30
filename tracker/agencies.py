"""The agencies we track. This list is the source of truth; each run syncs it
into the `agencies` table."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Agency:
    id: str
    name: str
    short_name: str
    url: str


AGENCIES: list[Agency] = [
    Agency("sbe", "State Board of Education", "SBE",
           "https://www.cde.ca.gov/be/ag/ag/index.asp"),
    Agency("accs", "Advisory Commission on Charter Schools", "ACCS",
           "https://www.cde.ca.gov/be/cc/cs/accsagendas.asp"),
    Agency("opsc", "Office of Public School Construction", "OPSC",
           "https://www.dgs.ca.gov/OPSC/Meetings"),
    Agency("ctc", "Commission on Teacher Credentialing", "CTC",
           "https://meetings.ctc.ca.gov/"),
    Agency("csfa", "California School Finance Authority", "CSFA",
           "https://www.treasurer.ca.gov/csfa/meeting"),
    Agency("fcc", "Federal Communications Commission", "FCC",
           "https://www.fcc.gov/news-events/events/open-commission-meetings"),
    Agency("calpers", "CalPERS Board", "CalPERS",
           "https://www.calpers.ca.gov/about/board/board-meetings"),
    Agency("calstrs", "CalSTRS Board", "CalSTRS",
           "https://www.calstrs.com/board-meetings"),
    Agency("cpag", "California Practitioners Advisory Group", "CPAG",
           "https://www.cde.ca.gov/be/cc/cp/"),
    Agency("fppc", "Fair Political Practices Commission", "FPPC",
           "https://www.fppc.ca.gov/about-fppc/commission-hearings/"),
    Agency("ccee", "California Collaborative for Educational Excellence", "CCEE",
           "https://ccee-ca.org/governing-board/meetings/"),
    Agency("eaap", "Educational Audit Appeals Panel", "EAAP",
           "https://eaap.ca.gov/panel/agendas/"),
    Agency("ag_opinions", "Attorney General Legal Opinions", "AG Opinions",
           "https://oag.ca.gov/opinions/monthly-report"),
    Agency("ag_initiatives", "Attorney General Ballot Initiatives", "AG Initiatives",
           "https://oag.ca.gov/initiatives/active-measures"),
]

BY_ID = {a.id: a for a in AGENCIES}
