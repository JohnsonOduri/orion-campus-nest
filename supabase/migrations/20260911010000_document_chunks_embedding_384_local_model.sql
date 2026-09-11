-- No embedding-capable API key is configured for this project; switch to a
-- free local model (sentence-transformers/all-MiniLM-L6-v2, 384 dims)
-- instead of the OpenAI-shaped 1536-dim column. Table was empty (0 rows) at
-- the time of this change, so it is a safe in-place type change, not a data
-- migration.
drop index if exists chunks_embedding_hnsw_idx;

alter table public.document_chunks
  alter column embedding type vector(384);

create index chunks_embedding_hnsw_idx
  on public.document_chunks using hnsw (embedding vector_cosine_ops);

comment on column public.document_chunks.embedding is
  'sentence-transformers/all-MiniLM-L6-v2 (384-dim, local, free) — see scripts/ingest_documents.py';
