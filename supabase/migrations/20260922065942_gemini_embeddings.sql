-- ORION — Gemini embeddings (gemini-embedding-2, 768-dim), additive.
--
-- Moves semantic retrieval off the in-process MiniLM model so the API no
-- longer needs torch/sentence-transformers (docs/embeddings.md).
--
-- Strictly additive so the MiniLM path stays a working rollback target:
--   * document_chunks.embedding (vector(384), MiniLM) and
--     match_document_chunks(vector(384), ...) are NOT touched.
--   * a parallel document_chunks.embedding_gemini vector(768) column is
--     filled by scripts/reembed_gemini.py (resumable: NULL = not yet done).
--   * match_document_chunks_gemini has exactly the same filters and
--     security model as match_document_chunks (security invoker -> RLS
--     still applies; active documents only; validity window vs as_of).
--   * faculty.research_embedding stores the research-interest vector once,
--     replacing the per-request re-embedding of the whole faculty corpus.
--
-- Staleness guards: a vector must never be served for text it was not
-- computed from. If content / research_interests changes in an UPDATE that
-- does not also supply a new vector, the vector is reset to NULL (and the
-- re-embed script picks the row up again).

-- ------------------------------------------------------------ document_chunks

alter table public.document_chunks
  add column if not exists embedding_gemini vector(768);

comment on column public.document_chunks.embedding_gemini is
  'gemini-embedding-2, output_dimensionality=768, input "title: <doc title[ / section]> | text: <chunk>" '
  '(backend/query/embeddings.py). NULL = not yet embedded; see scripts/reembed_gemini.py.';

create index if not exists chunks_embedding_gemini_hnsw_idx
  on public.document_chunks using hnsw (embedding_gemini vector_cosine_ops);

create or replace function public.document_chunks_reset_stale_embedding()
returns trigger
language plpgsql
set search_path = public
as $$
begin
  if new.content is distinct from old.content then
    if new.embedding_gemini is not distinct from old.embedding_gemini then
      new.embedding_gemini := null;
    end if;
    if new.embedding is not distinct from old.embedding then
      new.embedding := null;
    end if;
  end if;
  return new;
end;
$$;

drop trigger if exists document_chunks_reset_stale_embedding on public.document_chunks;
create trigger document_chunks_reset_stale_embedding
  before update of content on public.document_chunks
  for each row execute function public.document_chunks_reset_stale_embedding();

revoke execute on function public.document_chunks_reset_stale_embedding() from public, anon, authenticated;

create or replace function public.match_document_chunks_gemini(
  query_embedding vector(768),
  match_count int default 5,
  filter_cohort text default null,
  filter_category text default null,
  filter_document_type text default null,
  as_of date default current_date
)
returns table (
  chunk_id bigint,
  document_id bigint,
  title text,
  section_title text,
  content text,
  page_start int,
  page_end int,
  similarity float8,
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
    dc.id,
    dc.document_id,
    d.title,
    dc.section_title,
    dc.content,
    dc.page_start,
    dc.page_end,
    1 - (dc.embedding_gemini <=> query_embedding) as similarity,
    dc.metadata->>'cohort',
    dc.metadata->>'category',
    dc.metadata->>'document_type',
    d.valid_from,
    d.valid_until
  from document_chunks dc
  join documents d on d.id = dc.document_id
  where d.status = 'active'
    and dc.embedding_gemini is not null
    and (filter_cohort is null or dc.metadata->>'cohort' = filter_cohort)
    and (filter_category is null or dc.metadata->>'category' = filter_category)
    and (filter_document_type is null or dc.metadata->>'document_type' = filter_document_type)
    and (d.valid_from is null or d.valid_from <= as_of)
    and (d.valid_until is null or d.valid_until >= as_of)
  order by dc.embedding_gemini <=> query_embedding
  limit match_count;
$$;

revoke execute on function public.match_document_chunks_gemini(vector, int, text, text, text, date) from public, anon;
grant execute on function public.match_document_chunks_gemini(vector, int, text, text, text, date) to authenticated;

-- -------------------------------------------------------------------- faculty

alter table public.faculty
  add column if not exists research_embedding vector(768);

comment on column public.faculty.research_embedding is
  'gemini-embedding-2 (768-dim) of research_interests, input "title: none | text: <research_interests>". '
  'Computed once at ingestion by scripts/reembed_gemini.py --target faculty; reset to NULL when research_interests changes.';

create or replace function public.faculty_reset_stale_research_embedding()
returns trigger
language plpgsql
set search_path = public
as $$
begin
  if new.research_interests is distinct from old.research_interests
     and new.research_embedding is not distinct from old.research_embedding then
    new.research_embedding := null;
  end if;
  return new;
end;
$$;

drop trigger if exists faculty_reset_stale_research_embedding on public.faculty;
create trigger faculty_reset_stale_research_embedding
  before update of research_interests on public.faculty
  for each row execute function public.faculty_reset_stale_research_embedding();

revoke execute on function public.faculty_reset_stale_research_embedding() from public, anon, authenticated;

-- ~150 rows: an exact sequential scan is cheaper than maintaining an ANN
-- index and never misses a match, so no vector index here on purpose.
create or replace function public.match_faculty_research(
  query_embedding vector(768),
  match_count int default 5,
  min_similarity float8 default 0
)
returns table (
  id bigint,
  full_name text,
  initials text,
  email text,
  office_location text,
  office_hours text,
  research_interests text,
  similarity float8
)
language sql
stable
security invoker
set search_path = public, extensions
as $$
  select
    f.id,
    f.full_name,
    f.initials,
    f.email,
    f.office_location,
    f.office_hours,
    f.research_interests,
    1 - (f.research_embedding <=> query_embedding) as similarity
  from faculty f
  where f.status = 'active'
    and f.research_embedding is not null
    and 1 - (f.research_embedding <=> query_embedding) >= min_similarity
  order by f.research_embedding <=> query_embedding
  limit match_count;
$$;

revoke execute on function public.match_faculty_research(vector, int, float8) from public, anon;
grant execute on function public.match_faculty_research(vector, int, float8) to authenticated;
