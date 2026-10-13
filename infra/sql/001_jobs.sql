create table if not exists jobs (
  id              text primary key,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now(),
  finished_at     timestamptz,
  status          text not null,
  stages          jsonb not null,
  error           jsonb,
  source_id       text not null,
  source          jsonb not null,
  source_language text not null,
  preset          text not null,
  output_language text not null,
  options         text[] not null default '{}',
  email           text,
  consent_152fz   boolean not null default false,
  email_sent_at   timestamptz,
  result          jsonb,
  meta            jsonb,
  total_cost_usd  numeric(8,4)
);
create index if not exists jobs_status_idx on jobs(status);
create index if not exists jobs_created_idx on jobs(created_at desc);
