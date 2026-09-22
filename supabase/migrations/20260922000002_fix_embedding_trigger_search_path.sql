-- Fix for 20260922000001: the stale-vector triggers compare vector columns
-- (`is not distinct from`), and pgvector's `=` operator lives in the
-- `extensions` schema. With `search_path = public` every UPDATE of
-- document_chunks.content / faculty.research_interests failed with
-- 42883 "operator does not exist: extensions.vector = extensions.vector".
-- Found by a rolled-back trigger test before any real update hit it.

alter function public.document_chunks_reset_stale_embedding() set search_path = public, extensions;
alter function public.faculty_reset_stale_research_embedding() set search_path = public, extensions;
