-- Paced crawling for sites that limit automated requests (cde.ca.gov).

-- Small key/value store for crawler state (e.g. the CDE page queue and backoff).
create table public.crawl_state (
  key        text primary key,
  value      jsonb not null,
  updated_at timestamptz not null default now()
);

-- One row per request to a rate-limited host, so we can see which spacing
-- the site accepts.
create table public.crawl_log (
  id           bigint generated always as identity primary key,
  host         text not null,
  url          text not null,
  requested_at timestamptz not null default now(),
  gap_seconds  int,          -- time since the previous request to this host
  outcome      text not null check (outcome in ('ok', 'challenged', 'error')),
  detail       text
);
create index on public.crawl_log (host, requested_at desc);

alter table public.crawl_state enable row level security;
alter table public.crawl_log   enable row level security;
create policy "team read" on public.crawl_log for select to authenticated using (true);
