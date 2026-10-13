# Архитектура

Схема: `design/architecture-light.png` и `design/architecture-dark.png`, источник – `design/architecture-gen.py` (генерирует `.html` и `.svg`, затем `design/architecture-check.mjs` в headless Chromium меряет каждый `<text>` через `getBBox` против его бокса минус 12 px и только при чистой проверке пишет PNG 3840×2160; `python3 docs/design/architecture-gen.py docs/design`). Картина на 4 октября 2026, после захода G.

Слои, как в README:

1. Фронт (React + Vite + TS) – статика через nginx, общается только с `/api/`. Внутренний nginx считает лимиты по адресу (`X-Real-IP` от внешнего прокси), не пишет журнал запросов и не пробрасывает адрес в n8n.
2. Cloudflare Turnstile – виджет на форме запуска работает в браузере, токен уходит в `POST /api/jobs`, `jobs-api` проверяет его через siteverify без `remoteip` и сам отвергает повтор (`turnstile_used`). Режимы `off` / `monitor` / `enforce` строкой в `settings`.
3. n8n – шесть флоу: `jobs-api` (публичные вебхуки: probe, jobs, статус, retry, export, media, feedback, limits), `pipeline` (download → transcribe → clean → digest → extras → finalize, статусы и результат в Postgres), `llm-call` (один вызов модели: схема, правила, одна попытка исправления), `log-events` (события в таблицу `events`, вызов без ожидания), `on-error` (Error Workflow пайплайна: исключение в ноде закрывает задачу по `meta.execution_id`), `maintenance` (Schedule Trigger раз в час: результаты старше `RESULT_RETENTION_DAYS` обнуляются вместе с опознавательными полями, задачи старше `MAX_JOB_MINUTES` закрываются как `timeout`).
4. Media Service (FastAPI, docker) – probe, download (yt-dlp с Deno, ffmpeg), split по тишине, артефакты, чистка по `RETENTION_HOURS` и `PLAYBACK_RETENTION_DAYS`. Внутренний, за `X-API-Key`.
5. STT – Deepgram nova-3 (`POST /v1/listen`, бинарное аудио куска). `STT_PROVIDER` переключает на OpenAI-совместимый API или self-hosted (`local`).
6. LLM – gpt-4o-mini на clean и digest-map, gpt-5.6-luna на digest-reduce и critique; `LLM_BASE_URL` ведёт на локальную модель. Цены и признаки моделей – `n8n/pricing.json`.
7. Postgres – пять таблиц: `jobs`, `events`, `settings`, `feedback`, `turnstile_used` (`infra/sql/001–005`).

Снаружи: обратный прокси с TLS перед внутренним nginx, без журнала запросов; выкат по SHA коммита (`infra/deploy/`) – `self-hosting.md`, встраивание в чужую систему – `integration.md`.

Подробности: `contract-api.md` (кто кого вызывает, лимиты, ошибки), `result-schema.md` (что в результате), `TZ-media-service.md` (медиа-сервис), `design-brief.md` (экраны), `privacy-policy.md` (что куда уходит и сколько хранится).
