-- Выполни целиком в Supabase: SQL Editor -> New query -> Run

create table if not exists messages (
  id bigint generated always as identity primary key,
  chat_id bigint not null,
  role text not null,
  content text not null,
  ts timestamptz default now()
);
create index if not exists idx_messages_chat on messages(chat_id, id);

create table if not exists users (
  user_id bigint primary key,
  name text,
  role text default 'assistant',
  model text default 'chat',
  requests integer default 0,
  first_seen timestamptz default now()
);

create table if not exists emoji (plain text primary key, custom_id text not null);
create table if not exists meta (key text primary key, value text);
create table if not exists processed_updates (
  update_id bigint primary key,
  created_at timestamptz default now()
);

-- Бот ходит с service_role ключом (обходит RLS); для anon-ключа доступ закрыт.
alter table messages enable row level security;
alter table users enable row level security;
alter table emoji enable row level security;
alter table meta enable row level security;
alter table processed_updates enable row level security;

create or replace function increment_requests(p_user_id bigint) returns void
language sql as $$ update users set requests = requests + 1 where user_id = p_user_id; $$;

create or replace function bot_stats() returns json
language sql as $$
  select json_build_object(
    'users', (select count(*) from users),
    'requests', (select coalesce(sum(requests), 0) from users),
    'messages', (select count(*) from messages)
  );
$$;
