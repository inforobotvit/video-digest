-- Non-fatal events of the pipeline (contract section 4): what jobs.error and the n8n execution data do not keep.
-- Written by the log-events sub-workflow, read with psql. Old rows are deleted on every insert
-- (EVENTS_RETENTION_DAYS, default 7): there is no maintenance flow yet, so the cleanup rides along.
create table if not exists events (
  id          bigserial primary key,
  ts          timestamptz not null default now(),
  job_id      text,
  stage       text,
  type        text not null,        -- provider_auth | key_check_ok | key_check_failed | key_check_skipped | stt_language_rejected | stt_empty_result | clean_retention_low | source_busy | result_expired | job_timeout | schema_violation | extras_block_skipped | validator_retry
  level       text not null,        -- info | warn | error
  provider    text,
  model       text,
  http_status integer,
  body        text                  -- masked, at most 300 characters
);
create index if not exists events_ts_idx on events(ts desc);
create index if not exists events_job_idx on events(job_id);
