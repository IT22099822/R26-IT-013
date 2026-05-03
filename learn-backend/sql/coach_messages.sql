-- LEARN Coach chat log. Run once in the Supabase SQL editor.
-- The backend writes with the service key; RLS with no policies keeps the
-- table closed to the public anon key.
create table if not exists coach_messages (
  id              uuid primary key default gen_random_uuid(),
  student_id      uuid not null references students(student_id) on delete cascade,
  intervention_id uuid,
  role            text not null check (role in ('user', 'assistant')),
  content         text not null,
  created_at      timestamptz not null default now()
);
create index if not exists coach_messages_student_idx on coach_messages (student_id, created_at);
alter table coach_messages enable row level security;
