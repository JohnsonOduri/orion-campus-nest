-- Wraps the existing document_chunks pgvector corpus (scripts/ingest_documents.py)
-- for the query router's semantic retrieval (backend/query/retrieval.py).
-- security invoker so RLS still applies to the calling role, same pattern
-- as every orion_* RPC (docs/timetable.md §11).
create or replace function public.match_document_chunks(
  query_embedding vector(384),
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
    1 - (dc.embedding <=> query_embedding) as similarity,
    dc.metadata->>'cohort',
    dc.metadata->>'category',
    dc.metadata->>'document_type',
    d.valid_from,
    d.valid_until
  from document_chunks dc
  join documents d on d.id = dc.document_id
  where d.status = 'active'
    and (filter_cohort is null or dc.metadata->>'cohort' = filter_cohort)
    and (filter_category is null or dc.metadata->>'category' = filter_category)
    and (filter_document_type is null or dc.metadata->>'document_type' = filter_document_type)
    and (d.valid_from is null or d.valid_from <= as_of)
    and (d.valid_until is null or d.valid_until >= as_of)
  order by dc.embedding <=> query_embedding
  limit match_count;
$$;

grant execute on function public.match_document_chunks(vector, int, text, text, text, date) to authenticated;
