create extension if not exists "pgcrypto";

create table if not exists membros (
  id uuid primary key default gen_random_uuid(),
  nome text not null,
  nome_key text,
  whatsapp text,
  whatsapp_key text,
  disponibilidades jsonb not null default '[]'::jsonb
);

create unique index if not exists membros_whatsapp_key_unique
on membros (whatsapp_key)
where whatsapp_key is not null and whatsapp_key <> '';

create table if not exists campanhas (
  id text primary key,
  ano integer not null,
  mes integer not null,
  nome text not null,
  sabados jsonb not null default '[]'::jsonb,
  status text not null default 'arquivada',
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

create table if not exists escalas (
  id text primary key,
  campanha_id text not null references campanhas(id) on delete cascade,
  nome text not null,
  itens jsonb not null default '[]'::jsonb,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);
