-- The FastAPI insert (backend/app/api/ai.py) never sends user_id — per
-- CLAUDE.md §13 it must never trust a client-supplied id anyway. Without a
-- default the column landed NULL, which the RLS `with check (auth.uid() =
-- user_id)` policy correctly rejected: "new row violates row-level security
-- policy for table ai_conversations" on every /ai/ask call.
alter table public.ai_conversations alter column user_id set default auth.uid();
