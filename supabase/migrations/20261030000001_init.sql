-- California education regulatory agency tracker: core schema.
-- Targets Supabase (Postgres 15+). Relies on Supabase's `auth` schema
-- (auth.users, auth.uid()) and the `authenticated` role.

-- ---------------------------------------------------------------------------
-- Agencies and what we scrape from them
-- ---------------------------------------------------------------------------

create table public.agencies (
  id                   text primary key,          -- scraper key, e.g. 'sbe'
  name                 text not null,
  short_name           text not null,
  url                  text not null,
  active               boolean not null default true,
  scraper_ready        boolean not null default false,
  last_checked_at      timestamptz,
  last_success_at      timestamptz,
  last_error           text,
  consecutive_failures int not null default 0,
  last_posting_count   int
);

create type public.posting_kind as enum ('meeting', 'opinion', 'initiative');

-- One row per meeting agenda, AG opinion, or ballot initiative.
create table public.postings (
  id              bigint generated always as identity primary key,
  agency_id       text not null references public.agencies (id),
  kind            public.posting_kind not null default 'meeting',
  external_key    text not null,                 -- stable id within the agency
  title           text not null,
  meeting_date    date,
  url             text,
  content_hash    text not null,
  -- Loaded during an agency's first run; treated as already reviewed.
  is_baseline     boolean not null default false,
  first_seen_at   timestamptz not null default now(),
  last_changed_at timestamptz not null default now(),
  last_seen_at    timestamptz not null default now(),
  search          tsvector generated always as (to_tsvector('english', title)) stored,
  unique (agency_id, external_key)
);
create index on public.postings (agency_id, meeting_date desc);
create index on public.postings using gin (search);

create table public.items (
  id          bigint generated always as identity primary key,
  posting_id  bigint not null references public.postings (id) on delete cascade,
  position    int not null,
  number      text,
  title       text not null,
  description text,
  search      tsvector generated always as (
    to_tsvector('english', coalesce(number, '') || ' ' || title || ' ' || coalesce(description, ''))
  ) stored
);
create index on public.items (posting_id, position);
create index on public.items using gin (search);

-- Linked agendas, staff reports, attachments. item_position ties a document
-- to an agenda item without depending on item ids (items are rebuilt on change).
create table public.documents (
  id            bigint generated always as identity primary key,
  posting_id    bigint not null references public.postings (id) on delete cascade,
  item_position int,
  url           text not null,
  label         text,
  sha256        text,
  text          text,
  fetched_at    timestamptz,
  fetch_error   text,
  search        tsvector generated always as (
    to_tsvector('english', coalesce(label, '') || ' ' || coalesce(text, ''))
  ) stored,
  unique (posting_id, url)
);
create index on public.documents using gin (search);

-- New or changed postings, used for the activity feed and email alerts.
create table public.posting_events (
  id           bigint generated always as identity primary key,
  posting_id   bigint not null references public.postings (id) on delete cascade,
  kind         text not null check (kind in ('new', 'updated')),
  content_hash text not null,
  created_at   timestamptz not null default now()
);
create index on public.posting_events (created_at desc);

-- ---------------------------------------------------------------------------
-- People
-- ---------------------------------------------------------------------------

create table public.profiles (
  id           uuid primary key references auth.users (id) on delete cascade,
  email        text not null,
  display_name text
);

create function public.handle_new_user() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  insert into public.profiles (id, email) values (new.id, new.email)
  on conflict (id) do update set email = excluded.email;
  insert into public.user_prefs (user_id) values (new.id) on conflict do nothing;
  return new;
end $$;

create table public.user_prefs (
  user_id             uuid primary key references auth.users (id) on delete cascade,
  email_mode          text not null default 'none'
                      check (email_mode in ('none', 'daily', 'immediate')),
  -- null = all agencies
  agency_ids          text[],
  -- Only email about postings that have at least one keyword match.
  only_keyword_hits   boolean not null default false
);

create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

create table public.notifications_sent (
  user_id  uuid not null references auth.users (id) on delete cascade,
  event_id bigint not null references public.posting_events (id) on delete cascade,
  channel  text not null check (channel in ('immediate', 'daily')),
  sent_at  timestamptz not null default now(),
  primary key (user_id, event_id)
);

-- Review status is shared by the whole team.
create table public.reviews (
  id          bigint generated always as identity primary key,
  posting_id  bigint not null references public.postings (id) on delete cascade,
  user_id     uuid not null default auth.uid() references auth.users (id),
  reviewed_at timestamptz not null default now(),
  note        text
);
create index on public.reviews (posting_id, reviewed_at desc);
-- Lets the dashboard embed the reviewer's name: reviews?select=*,profiles(email,display_name)
alter table public.reviews
  add constraint reviews_profile_fk foreign key (user_id) references public.profiles (id);

-- ---------------------------------------------------------------------------
-- Keywords and matching
-- ---------------------------------------------------------------------------

create table public.keywords (
  id         bigint generated always as identity primary key,
  term       text not null check (length(trim(term)) > 0),
  -- word:   whole word(s), also matches plurals ("charter" -> "charters")
  -- phrase: exact words in order
  -- regex:  Postgres regular expression, case-insensitive
  match_type text not null default 'word' check (match_type in ('word', 'phrase', 'regex')),
  agency_id  text references public.agencies (id),   -- null = all agencies
  active     boolean not null default true,
  created_by uuid default auth.uid() references auth.users (id),
  created_at timestamptz not null default now()
);

create table public.matches (
  id          bigint generated always as identity primary key,
  keyword_id  bigint not null references public.keywords (id) on delete cascade,
  posting_id  bigint not null references public.postings (id) on delete cascade,
  item_id     bigint references public.items (id) on delete cascade,
  document_id bigint references public.documents (id) on delete cascade,
  source      text not null check (source in ('title', 'item', 'document')),
  hit_count   int not null,
  snippet     text not null
);
create index on public.matches (posting_id);
create index on public.matches (keyword_id);

create function public.keyword_pattern(term text, match_type text) returns text
language sql immutable as $$
  select case match_type
    when 'regex' then term
    else '\y'
      || regexp_replace(
           regexp_replace(trim(term), '([.^$*+?()\[\]{}|\\])', '\\\1', 'g'),
           '\s+', '\\s+', 'g')
      || case when match_type = 'word' then '(s|es|''s)?' else '' end
      || '\y'
  end
$$;

-- ~200 characters of context around the first match, whitespace collapsed.
create function public.match_snippet(body text, pattern text) returns text
language sql immutable as $$
  with p as (select regexp_instr(body, pattern, 1, 1, 0, 'i') as pos)
  select trim(regexp_replace(
           case when p.pos > 100 then '…' else '' end
           || substr(body, greatest(p.pos - 100, 1), 220)
           || case when length(body) > p.pos + 120 then '…' else '' end,
           '\s+', ' ', 'g'))
  from p
$$;

-- Recompute matches for the given postings (null = all) and keywords (null = all).
create function public.rematch(p_posting_ids bigint[], p_keyword_ids bigint[]) returns void
language plpgsql security definer set search_path = public as $$
begin
  delete from matches m
  where (p_posting_ids is null or m.posting_id = any (p_posting_ids))
    and (p_keyword_ids is null or m.keyword_id = any (p_keyword_ids));

  with kw as (
    select k.id, k.agency_id, keyword_pattern(k.term, k.match_type) as pat
    from keywords k
    where k.active and (p_keyword_ids is null or k.id = any (p_keyword_ids))
  ),
  scope as (
    select p.id as posting_id, kw.id as keyword_id, kw.pat
    from postings p
    join kw on kw.agency_id is null or kw.agency_id = p.agency_id
    where p_posting_ids is null or p.id = any (p_posting_ids)
  )
  insert into matches (keyword_id, posting_id, item_id, document_id, source, hit_count, snippet)
  select s.keyword_id, s.posting_id, null::bigint, null::bigint, 'title',
         regexp_count(p.title, s.pat, 1, 'i'), match_snippet(p.title, s.pat)
  from scope s join postings p on p.id = s.posting_id
  where p.title ~* s.pat
  union all
  select s.keyword_id, s.posting_id, i.id, null::bigint, 'item',
         regexp_count(t.body, s.pat, 1, 'i'), match_snippet(t.body, s.pat)
  from scope s
  join items i on i.posting_id = s.posting_id
  cross join lateral (
    select concat_ws(' ', i.number, i.title, i.description) as body
  ) t
  where t.body ~* s.pat
  union all
  select s.keyword_id, s.posting_id, null::bigint, d.id, 'document',
         regexp_count(t.body, s.pat, 1, 'i'), match_snippet(t.body, s.pat)
  from scope s
  join documents d on d.posting_id = s.posting_id
  cross join lateral (
    select concat_ws(' ', d.label, d.text) as body
  ) t
  where t.body ~* s.pat;
end $$;

-- Adding or editing a keyword immediately searches everything already stored.
create function public.keywords_rematch_trigger() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  if new.match_type = 'regex' then
    perform '' ~* new.term;   -- raises a clear error for an invalid pattern
  end if;
  perform rematch(null, array[new.id]);
  return new;
end $$;

create trigger keywords_rematch
  after insert or update of term, match_type, agency_id, active on public.keywords
  for each row execute function public.keywords_rematch_trigger();

-- ---------------------------------------------------------------------------
-- Dashboard view
-- ---------------------------------------------------------------------------

create view public.posting_status with (security_invoker = true) as
select
  p.*,
  a.short_name as agency_short_name,
  a.name       as agency_name,
  r.reviewed_at as last_reviewed_at,
  r.user_id     as last_reviewed_by,
  pr.email      as last_reviewed_by_email,
  pr.display_name as last_reviewed_by_name,
  case
    when r.reviewed_at is null and not p.is_baseline then 'new'
    when p.last_changed_at > coalesce(r.reviewed_at, p.first_seen_at) then 'updated'
    when r.reviewed_at is null then 'baseline'
    else 'reviewed'
  end as status,
  coalesce(mc.match_count, 0) as match_count,
  coalesce(mc.keywords, '{}') as matched_keywords
from public.postings p
join public.agencies a on a.id = p.agency_id
left join lateral (
  select rv.reviewed_at, rv.user_id from public.reviews rv
  where rv.posting_id = p.id order by rv.reviewed_at desc limit 1
) r on true
left join public.profiles pr on pr.id = r.user_id
left join lateral (
  select sum(m.hit_count)::int as match_count,
         array_agg(distinct k.term order by k.term) as keywords
  from public.matches m join public.keywords k on k.id = m.keyword_id
  where m.posting_id = p.id
) mc on true;

-- Full-text search across postings, items and documents.
create function public.search_all(q text, p_agency_id text default null,
                                  p_from date default null, p_to date default null)
returns table (posting_id bigint, source text, item_id bigint, document_id bigint,
               headline text, rank real)
language sql stable security invoker set search_path = public as $$
  with query as (select websearch_to_tsquery('english', q) as tsq),
  hits as (
    select p.id, 'title'::text, null::bigint, null::bigint,
           ts_headline('english', p.title, query.tsq), ts_rank(p.search, query.tsq)
    from postings p, query where p.search @@ query.tsq
    union all
    select i.posting_id, 'item', i.id, null,
           ts_headline('english', concat_ws(' ', i.number, i.title, i.description), query.tsq,
                       'MaxFragments=2'),
           ts_rank(i.search, query.tsq)
    from items i, query where i.search @@ query.tsq
    union all
    select d.posting_id, 'document', null, d.id,
           ts_headline('english', coalesce(d.text, d.label, ''), query.tsq, 'MaxFragments=2'),
           ts_rank(d.search, query.tsq)
    from documents d, query where d.search @@ query.tsq
  )
  select h.* from hits h (posting_id, source, item_id, document_id, headline, rank)
  join postings p on p.id = h.posting_id
  where (p_agency_id is null or p.agency_id = p_agency_id)
    and (p_from is null or p.meeting_date >= p_from)
    and (p_to is null or p.meeting_date <= p_to)
  order by h.rank desc
  limit 200
$$;

-- ---------------------------------------------------------------------------
-- Row-level security: any signed-in team member can read everything; the
-- scraper writes with the service role / direct DB connection, which bypasses RLS.
-- Turn off public sign-ups in Supabase Auth so only invited users get in.
-- ---------------------------------------------------------------------------

alter table public.agencies           enable row level security;
alter table public.postings           enable row level security;
alter table public.items              enable row level security;
alter table public.documents          enable row level security;
alter table public.posting_events     enable row level security;
alter table public.profiles           enable row level security;
alter table public.user_prefs         enable row level security;
alter table public.notifications_sent enable row level security;
alter table public.reviews            enable row level security;
alter table public.keywords           enable row level security;
alter table public.matches            enable row level security;

create policy "team read" on public.agencies       for select to authenticated using (true);
create policy "team read" on public.postings       for select to authenticated using (true);
create policy "team read" on public.items          for select to authenticated using (true);
create policy "team read" on public.documents      for select to authenticated using (true);
create policy "team read" on public.posting_events for select to authenticated using (true);
create policy "team read" on public.profiles       for select to authenticated using (true);
create policy "team read" on public.reviews        for select to authenticated using (true);
create policy "team read" on public.keywords       for select to authenticated using (true);
create policy "team read" on public.matches        for select to authenticated using (true);

create policy "own profile" on public.profiles for update to authenticated
  using (id = auth.uid()) with check (id = auth.uid());
create policy "own prefs" on public.user_prefs for all to authenticated
  using (user_id = auth.uid()) with check (user_id = auth.uid());
create policy "review as self" on public.reviews for insert to authenticated
  with check (user_id = auth.uid());
create policy "delete own review" on public.reviews for delete to authenticated
  using (user_id = auth.uid());
create policy "team edits keywords" on public.keywords for all to authenticated
  using (true) with check (true);

-- Starter keywords; the team can edit or remove these in the dashboard.
-- (The rematch trigger runs on insert; with no postings yet it is a no-op.)
insert into public.keywords (term, match_type, created_by) values
  ('charter', 'word', null),
  ('SB 740', 'phrase', null),
  ('Prop(osition)?\.?\s*39\y', 'regex', null);
