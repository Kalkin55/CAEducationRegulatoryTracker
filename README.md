# CA Education Agency Tracker

Watches California education-related agencies' meeting pages, plus AG opinions and ballot
initiatives. It flags new or changed agendas, searches agenda items and linked documents for
the team's keywords, and tracks which postings someone has reviewed.

```
GitHub Actions (every 2h) ──► Python scrapers ──► Supabase Postgres ◄── Dashboard (GitHub Pages)
                                    │                   ▲
                                    └──► Resend email   └── Supabase Auth (invite-only logins)
```

## Status

| Part | State |
|---|---|
| Database schema, keyword matching, review status, search, access rules | Done, tested |
| Pipeline: change detection, document text extraction, failure tracking | Done, tested |
| Email: immediate alerts, daily digest, scraper-failure alerts | Done, tested |
| Dashboard: inbox, posting detail, agencies, keywords, search, settings | Done |
| Per-agency scrapers | **Not started.** Waiting on network access to the agency sites (see below) |

Until an agency has a scraper, the dashboard shows it as "Not automated yet: check by hand".

## How it behaves

- **New / Updated since review / Reviewed:** review status is shared across the team. If a
  reviewed agenda later changes (an item is added, or a linked PDF is revised), it moves back to
  **Updated since review**.
- **First run:** when an agency is scraped for the first time, its past meetings are loaded as
  "Already posted" so the inbox doesn't start with hundreds of items. Upcoming meetings still
  show as **New**.
- **Keywords:** these are matched against posting titles, agenda items, and the text of linked
  PDFs, HTML pages and .docx files. There are three match types:
  - *Word:* the whole word, plurals included ("charter" matches "charters" but not "chartered").
  - *Exact phrase.*
  - *Regex.*

  A keyword can apply to all agencies or to one. Adding a keyword also searches everything
  already collected.
- **Documents:** linked documents are re-downloaded for meetings up to 14 days in the past, so
  revised agendas and late attachments are caught. If a download fails, the last good copy is
  kept.
- **Scraper health:** an agency counts as failing if its scraper errors, or suddenly finds
  nothing. After 3 failures in a row, it shows a red badge in the dashboard and `ADMIN_EMAILS`
  get an email.
- **Email:** each person chooses no email, a daily digest (about 7am Pacific), or immediate
  alerts. They can also limit alerts to certain agencies, or to postings with keyword matches.

## Setup

### 1. Supabase (database and logins, free tier)
1. Create a project at https://supabase.com.
2. Apply the migration: in the SQL Editor, run `supabase/migrations/20261030000001_init.sql`.
   Alternatively, use `supabase db push` with the Supabase CLI.
3. Under **Authentication → Sign In / Providers**, turn **off** "Allow new users to sign up".
   Then invite each team member from **Authentication → Users → Invite user**.
4. Under **Authentication → URL Configuration**, set the Site URL to your dashboard's URL
   (from step 3 below).
5. Note down three values:
   - Project URL and anon key: **Project Settings → API**.
   - Database connection string: **Connect → Session pooler**. This is `DATABASE_URL`.

### 2. Resend (email, free tier)
Create an account at https://resend.com, verify a sending domain (or use their test sender
while trying it out), and create an API key.

### 3. GitHub repository
1. Push this code to a GitHub repo.
2. **Settings → Secrets and variables → Actions**, then add:
   - **Secrets:** `DATABASE_URL`, `RESEND_API_KEY`, `EMAIL_FROM` (e.g.
     `Agency Tracker <tracker@yourdomain.org>`), `ADMIN_EMAILS` (comma-separated).
   - **Variables:** `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `DASHBOARD_URL` (e.g.
     `https://yourorg.github.io/ca-ed-tracker`), and optionally `TRACKER_USER_AGENT` with a
     contact address so agencies can reach you.
3. Under **Settings → Pages**, set Source to **GitHub Actions**. The **Deploy dashboard**
   workflow then publishes the site.
4. **Check agencies** runs on its schedule. To run it now, open **Actions → Check agencies →
   Run workflow**.

## Development

```bash
python -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"
```

Tests need a Postgres server where they can create databases:

```bash
TEST_ADMIN_DATABASE_URL=postgresql://postgres@localhost:5432/postgres pytest
```

See what the scrapers find, without needing a database:

```bash
python -m tracker run --no-db --agency sbe
```

Run the full pipeline against the database, then roll everything back (it prints any keyword
matches):

```bash
python -m tracker run --dry-run --agency sbe
```

Dashboard:

```bash
cd web && cp .env.example .env.local   # fill in the Supabase URL and anon key
npm install && npm run dev
```

### Adding a scraper

Create `tracker/scrapers/<agency>.py` with a class that subclasses `Scraper`, sets `agency_id`,
and implements `fetch(fetcher) -> list[Posting]`. Register it with the `@register` decorator,
and import the module at the bottom of `tracker/scrapers/__init__.py`.

A scraper only describes what the listing page shows: postings, their items, and document
links. The pipeline handles downloading, change detection, matching and alerts. Save a copy of
the agency's page under `tests/fixtures/<agency>/` and test the scraper against it, so a site
redesign shows up as a failing test rather than silently missing agendas.
