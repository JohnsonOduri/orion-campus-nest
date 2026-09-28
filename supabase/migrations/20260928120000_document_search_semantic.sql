-- Semantic (vector) retrieval over document_chunks, for hybrid search.
--
-- Why: full-text search matches words, not meaning. "What are the
-- examination hall rules?" matched a textbook reference to "Prentice Hall"
-- in a curriculum (AI-Tests/, 2026-09-25) — the words overlapped, the
-- meaning didn't. Every chunk now has a Gemini vector (embedding_gemini,
-- backfill finished 2026-09-23), so backend/query/documents.search() fuses
-- this ranking with search_document_chunks'.
--
-- The filters are deliberately IDENTICAL to search_document_chunks
-- (migration 20260922110000): active documents only, validity window,
-- cohort isolation through orion_cohort_family (CLAUDE.md §20), optional
-- category/document_type. Adding a second retrieval path must not open a
-- second, looser path around cohort isolation.
--
-- Additive and idempotent. SECURITY INVOKER: RLS still applies. EXECUTE for
-- signed-in users only, like search_document_chunks (20260922120000).

create or replace function public.search_document_chunks_semantic(
  query_embedding vector(768),
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
  similarity double precision,
  cohort text,
  category text,
  document_type text,
  valid_from date,
  valid_until date
)
language sql
stable
security invoker
set search_path = public, extensions
as $$
  select
    c.id,
    c.document_id,
    c.chunk_index,
    c.content,
    d.title,
    c.section_title,
    c.page_start,
    c.page_end,
    1 - (c.embedding_gemini <=> query_embedding) as similarity,
    d.cohort,
    d.category,
    d.document_type,
    d.valid_from,
    d.valid_until
  from public.document_chunks c
  join public.documents d on d.id = c.document_id
  where c.embedding_gemini is not null
    and d.status = 'active'
    and (d.valid_from is null or d.valid_from <= as_of)
    and (d.valid_until is null or d.valid_until >= as_of)
    and (
      search_document_chunks_semantic.cohort_family is null
      or d.cohort is null
      or public.orion_cohort_family(d.cohort) = search_document_chunks_semantic.cohort_family
    )
    and (filter_category is null or d.category = filter_category)
    and (filter_document_type is null or d.document_type = filter_document_type)
  order by c.embedding_gemini <=> query_embedding
  limit greatest(1, least(coalesce(match_count, 8), 30));
$$;

revoke execute on function public.search_document_chunks_semantic(vector, integer, text, text, text, date) from public, anon;
grant execute on function public.search_document_chunks_semantic(vector, integer, text, text, text, date) to authenticated;
