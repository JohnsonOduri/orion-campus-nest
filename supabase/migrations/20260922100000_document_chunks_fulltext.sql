-- Lexical (full-text) retrieval over document_chunks — docs/query-router.md.
--
-- Why: semantic retrieval depended entirely on Gemini embeddings, and the
-- documents students ask about most (both UG Regulations, Hostel Rules, the
-- anti-ragging documents, transcript/certificate procedures) have NO Gemini
-- vector yet (backfill stopped at the free-tier daily cap — todo.md B). Every
-- regulation/hostel question therefore answered "no information". Postgres
-- full-text search needs no model, no API key and no quota, and on this
-- corpus it finds the right clause directly (e.g. "minimum attendance" ->
-- R.6.1 / R.5.1, verified before writing this migration).
--
-- Additive and idempotent. SECURITY INVOKER: RLS on documents /
-- document_chunks still applies to the caller.

alter table public.document_chunks
  add column if not exists fts tsvector
  generated always as (
    setweight(to_tsvector('english', coalesce(section_title, '')), 'A') ||
    setweight(to_tsvector('english', coalesce(content, '')), 'B')
  ) stored;

create index if not exists document_chunks_fts_idx on public.document_chunks using gin (fts);

-- The corpus labels regulation cohorts three different ways ('21-25',
-- '2021_2025' on student_profiles, 'ADM2026' / '26-onwards'). Normalise them
-- to one family so cohort isolation (CLAUDE.md §20) can't be defeated by a
-- spelling difference.
create or replace function public.orion_cohort_family(p_cohort text)
returns text
language sql
immutable
set search_path = public
as $$
  select case
    when p_cohort is null or btrim(p_cohort) = '' then null
    when p_cohort ~ '(^|[^0-9])(20)?21[^0-9]+(20)?25([^0-9]|$)' then '21-25'
    when p_cohort ~ '(^|[^0-9])(20)?26([^0-9]|$)' then '26-onwards'
    else lower(btrim(p_cohort))
  end
$$;

create or replace function public.search_document_chunks(
  query_text text,
  match_count integer default 8,
  cohort_family text default null,
  filter_category text default null,
  filter_document_type text default null,
  as_of date default current_date
)
returns table (
  chunk_id bigint,
  document_id bigint,
  chunk_index integer,
  content text,
  title text,
  section_title text,
  page_start integer,
  page_end integer,
  rank real,
  cohort text,
  category text,
  document_type text,
  valid_from date,
  valid_until date
)
language plpgsql
stable
security invoker
set search_path = public
as $$
declare
  -- plainto_tsquery stems + drops stopwords but ANDs every term; a natural
  -- question ("what time should I be back in the hostel") rarely has every
  -- word in one chunk, so OR the lexemes and let ranking decide.
  v_query tsquery := replace(plainto_tsquery('english', coalesce(query_text, ''))::text, '&', '|')::tsquery;
begin
  if numnode(v_query) = 0 then
    return;
  end if;

  return query
  select
    c.id,
    c.document_id,
    c.chunk_index,
    c.content,
    d.title,
    c.section_title,
    c.page_start,
    c.page_end,
    (ts_rank_cd(c.fts, v_query, 32) + 0.5 * ts_rank(to_tsvector('english', d.title), v_query))::real as rank,
    d.cohort,
    d.category,
    d.document_type,
    d.valid_from,
    d.valid_until
  from public.document_chunks c
  join public.documents d on d.id = c.document_id
  where c.fts @@ v_query
    and d.status = 'active'
    and (d.valid_from is null or d.valid_from <= as_of)
    and (d.valid_until is null or d.valid_until >= as_of)
    and (
      search_document_chunks.cohort_family is null
      or d.cohort is null
      or public.orion_cohort_family(d.cohort) = search_document_chunks.cohort_family
    )
    and (filter_category is null or d.category = filter_category)
    and (filter_document_type is null or d.document_type = filter_document_type)
  order by rank desc
  limit greatest(1, least(coalesce(match_count, 8), 30));
end;
$$;

grant execute on function public.search_document_chunks(text, integer, text, text, text, date) to authenticated;
grant execute on function public.orion_cohort_family(text) to authenticated;
