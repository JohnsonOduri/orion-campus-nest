-- AI chat conversation persistence (CLAUDE.md §13: RLS is the real
-- boundary, request-scoped client only, auth.uid() authoritative).
--
-- Two tables: ai_conversations (one row per chat thread) and ai_messages
-- (one row per turn). Ownership is enforced by RLS alone — no RPC needed,
-- the FastAPI service reads/writes these through the caller's own
-- request-scoped Supabase client (backend/app/services/supabase_clients.py).

create table public.ai_conversations (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  title text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.ai_messages (
  id uuid primary key default gen_random_uuid(),
  conversation_id uuid not null references public.ai_conversations(id) on delete cascade,
  role text not null check (role in ('user', 'assistant')),
  content text not null,
  route text,
  created_at timestamptz not null default now()
);

create index ai_conversations_user_updated_idx on public.ai_conversations (user_id, updated_at desc);
create index ai_messages_conversation_created_idx on public.ai_messages (conversation_id, created_at);

alter table public.ai_conversations enable row level security;
alter table public.ai_messages enable row level security;

create policy "own conversations" on public.ai_conversations
  for all
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

-- Messages have no user_id of their own; ownership is derived through the
-- parent conversation, same pattern as timetable_entry_faculty deriving
-- visibility through timetable_entries.
create policy "own conversation messages" on public.ai_messages
  for all
  using (exists (
    select 1 from public.ai_conversations c
    where c.id = ai_messages.conversation_id and c.user_id = auth.uid()
  ))
  with check (exists (
    select 1 from public.ai_conversations c
    where c.id = ai_messages.conversation_id and c.user_id = auth.uid()
  ));

create trigger ai_conversations_set_updated_at
  before update on public.ai_conversations
  for each row execute function update_updated_at();
