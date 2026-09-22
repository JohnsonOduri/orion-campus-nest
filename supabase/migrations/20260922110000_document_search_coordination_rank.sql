-- Better ranking for search_document_chunks (20260922100000).
--
-- ts_rank_cd alone rewards a chunk that repeats ONE query word many times:
-- every anti-ragging chunk says "ragging" dozens of times, so "What counts as
-- ragging?" never reached the clause that defines it ("3. What constitutes
-- Ragging…"). Rank first by coordination — the share of DISTINCT query terms
-- a chunk contains — then by ts_rank_cd. Measured on the live corpus before
-- writing this: the definition clause moves from outside the top 8 to #2,
-- the punishment clause to #1; attendance/hostel questions keep their right
-- top hit. Same signature; SECURITY INVOKER; RLS still applies.

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
  v_query tsquery := replace(plainto_tsquery('english', coalesce(query_text, ''))::text, '&', '|')::tsquery;
  v_lexemes text[] := tsvector_to_array(to_tsvector('english', coalesce(query_text, '')));
  v_n integer := greatest(1, coalesce(array_length(tsvector_to_array(to_tsvector('english', coalesce(query_text, ''))), 1), 1));
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
    (
      (select count(distinct l) from unnest(tsvector_to_array(c.fts)) l where l = any(v_lexemes))::real / v_n
      + 0.5 * ts_rank_cd(c.fts, v_query, 32)
      + 0.3 * ts_rank(to_tsvector('english', d.title), v_query)
    )::real as rank,
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
