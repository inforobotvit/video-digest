-- Runtime limits as data (decision 2026-09-16, step C of the release plan): DAILY_BUDGET_USD and its neighbours
-- are read by n8n from the environment at container start, so raising a limit meant recreating the container
-- and killing the running jobs. A row here wins over the variable and takes effect on the next request; no row
-- means the variable applies, as before. Read inside the queries that already run (Load budget in jobs-api,
-- Load limits on /api/probe, Stuck jobs in maintenance), never as a separate round trip.
--
--   insert into settings (key, value) values ('DAILY_BUDGET_USD', '20')
--     on conflict (key) do update set value = excluded.value, updated_at = now();
--   delete from settings where key = 'DAILY_BUDGET_USD';   -- back to the variable
--
-- Keys: DAILY_BUDGET_USD | MAX_CONCURRENT_JOBS | MAX_DURATION_SEC | MAX_JOB_MINUTES. A value that is not a
-- number is ignored (the variable applies) rather than breaking job creation.
create table if not exists settings (
  key        text primary key,
  value      text not null,
  updated_at timestamptz not null default now()
);
