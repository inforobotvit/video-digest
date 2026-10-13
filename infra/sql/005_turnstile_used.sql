-- Replay guard for Turnstile tokens (step E3, 2026-09-29). A token is meant to be single-use and to live five
-- minutes, but siteverify accepted the same token three times in a row on 2026-09-28 (localhost widget), so the
-- guard is ours: the sha256 of every verified token is kept for ten minutes, a second use is turnstile_failed
-- with error code duplicate. Only hashes are stored, never tokens; rows older than ten minutes go on every insert.
create table if not exists turnstile_used (
  token_hash text primary key,
  used_at    timestamptz not null default now()
);
