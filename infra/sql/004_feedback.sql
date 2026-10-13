-- UMUX-Lite feedback from the result page (step E2, 2026-09-23): two agreement scores 1..5 and an optional comment,
-- one answer per job. Written by POST /api/feedback (jobs-api), read with psql (deploy-guide, the day of the post).
-- The comment field is labelled «no personal data» on the page; nothing here is deleted by retention.
create table if not exists feedback (
  job_id     text primary key,     -- one answer per job; a second POST gets 409 already_rated
  fits       smallint not null check (fits between 1 and 5),   -- «Возможности сервиса соответствуют моим требованиям»
  easy       smallint not null check (easy between 1 and 5),   -- «Сервисом легко пользоваться»
  comment    text check (comment is null or length(comment) <= 500),
  via        text not null check (via in ('timer', 'button')), -- how the form was opened
  created_at timestamptz not null default now()
);
