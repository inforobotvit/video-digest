# Интеграция

Для инженеров, которые решают, как встроить Video Digest в свою систему: поднять целиком в своём контуре, взять только движок под свой интерфейс или подавать записи файлами из своего хранилища. Как поднять сам сервис – `self-hosting.md`. Контракт API целиком – `contract-api.md`, смысл полей результата – `result-schema.md`.

## Коротко

Сервис превращает ссылку на видео или файл до 90 минут в очищенный транскрипт и выжимку с таймкодами: JSON по схеме `schemas/result.schema.json`, экспорт в md/srt/html/pdf, страница с плеером. Работает как один Docker Compose: nginx с фронтом, n8n с шестью флоу, медиа-сервис на FastAPI (yt-dlp, ffmpeg), Postgres, Gotenberg. Наружу ходит в три места, и все три заменяемы: STT и LLM – любым OpenAI-совместимым сервером через `STT_BASE_URL` и `LLM_BASE_URL`, проверка браузера Cloudflare Turnstile выключается строкой `settings`. Чтобы всё жило внутри контура, нужны chat-модель с контекстом от 32 тыс. токенов и устойчивым JSON, STT с сегментами, выход к видеоплатформам или вход файлами и аутентификация перед nginx – в самом сервисе её нет.

## Что на входе и на выходе

**Вход.** Ссылка на публичное видео YouTube, VK Видео, Rutube или прямая ссылка на медиафайл (http/https; медиа-сервис проверяет редиректы и не ходит на внутренние адреса), либо файл `mp4 mov mkv webm mp3 m4a wav ogg flac` до 200 МБ. Длительность до 90 минут; источник без определимой длительности отвергается. Если у видео есть ручные субтитры на языке видео, транскрибации нет – берутся субтитры; автосубтитры не используются.

**Выход.** JSON с полями `source`, `preset`, `options`, `output_language`, `transcript` (сырые сегменты и очищенные абзацы с таймкодами), `digest` (`tldr`, `structure`, `key_points`, `quotes`), `extras` по заказанным блокам, `meta` (стоимость, модели и токены по этапам, предупреждения), `notices` (оговорки к транскрипту). Экспорт из того же JSON на лету: `digest.md`, `transcript.md`, `transcript.srt`, `digest.html`, `digest.pdf`, `all.zip`.

**Пресеты и блоки.** Пресет (`plain`, `lecture`, `talk`, `interview`, `meeting`) задаёт акцент промптов и умолчания для шести блоков: `glossary`, `critique`, `self_check`, `decisions`, `action_items`, `questions`. В задачу уходит итоговый список `options`. Язык результата – `output_language` (ISO 639-1); выжимка пишется сразу на нём, транскрипт остаётся на языке видео.

**Что проверяет код** (правила раздела 9 `result-schema.md`): ответ модели – JSON по схеме, невалидный возвращается модели один раз с текстом ошибки; таймкоды берутся из транскрипта, а не у модели; структура покрывает запись без дыр и наложений; цитата принимается, только если найдена в транскрипте дословно; на чистке транскрипта измеряется удержание, и кусок с потерями уходит на исправление, а оставшиеся потери показываются читателю оговоркой.

Чего нет: проверки фактов, диаризации наружу, перевода транскрипта целиком, аккаунтов, писем (поле есть в API, интерфейс его не собирает).

## API

Все ручки под `/api/`, JSON, ошибки – `{"error": {"code", "message"}}`. Полный список кодов, тел и заголовков – `contract-api.md`. Машинному клиенту хватает четырёх вызовов.

**1. Регистрация источника**
```
POST /api/probe
{"url": "https://www.youtube.com/watch?v=QOQRduGvZwc"}
→ 200 {"source_id": "a1b2c3d4e5f6", "platform": "youtube", "title": "…", "duration_sec": 3147,
       "subtitles": {"manual": [], "auto": ["ru"]}, "recommended": "transcribe", "language": "ru",
       "thumbnail_url": "…", "estimate": {"seconds": 312, "strategy": "transcribe",
       "per_option": {"glossary": 15, "critique": 30, "self_check": 15, "action_items": 15, "decisions": 15, "questions": 15}}}
```
Файл: тот же `POST /api/probe` multipart с полем `file`, ответ тот же с `platform: "upload"` и `language: null`. Отказы: 400 `unsupported_url`, 404 `private_or_removed`, 403 `bot_check`, 400 `too_long`, 400 `unknown_duration`, 413 `file_too_large`.

**2. Создание задачи**
```
POST /api/jobs
{"source_id": "a1b2c3d4e5f6", "source_language": "ru", "preset": "plain",
 "output_language": "ru", "options": ["glossary"]}
→ 202 {"job_id": "j_w6lagh", "status": "queued", "url": "/jobs/j_w6lagh"}
```
`turnstile_token` нужен только в режиме Turnstile `enforce`; при `off` не проверяется. Отказы: 400 `validation_error`, 404 `unknown_source`, 400 `too_long`, 429 `daily_limit`, 429 `busy`, 403 `bot_check_failed`, 500 `internal_error`.

**3. Статус и результат**
```
GET /api/jobs/j_w6lagh
→ 200 {"job_id": "j_w6lagh", "status": "processing", "created_at": "…", "finished_at": null,
       "estimate_sec": 327, "preset": "plain", "options": ["glossary"],
       "stages": [{"name": "download", "status": "done", "ms": 16407},
                  {"name": "transcribe", "status": "done", "progress": {"done": 6, "total": 6}, "ms": 34969},
                  {"name": "clean", "status": "running", "progress": {"done": 1, "total": 8}}, …],
       "source": {…}, "result": null, "error": null}
```
При `done` в `result` – JSON по схеме; при `failed` – `error: {"stage", "code", "message"}`. `done` с `result: null` – результат удалён по сроку хранения. Вебхука о готовности нет, только опрос; разумный шаг – 3 секунды.

**4. Экспорт** – `GET /api/jobs/{id}/export/{digest.md | transcript.md | transcript.srt | digest.html | digest.pdf | all.zip}`; 409 `not_ready` до `done`, 410 `gone` после удаления.

Остальное: `POST /api/jobs/{id}/retry`, `GET /api/jobs/{id}/media` (дорожка загруженного файла, с Range), `POST /api/feedback`, `GET /api/limits`.

**Лимиты nginx** по адресу клиента (`infra/nginx.conf`): создание задач 2 в минуту, probe 10 в минуту, статус 2 в секунду, экспорт 6 в минуту; отказ – 429 `rate_limited`. Для машинного клиента с одного адреса это мало: поднять зоны `jobs` и `status` или вынести клиента в отдельный `location` без `limit_req`, затем пересобрать образ `web` – конфиг внутри него.

Чего в API нет: аутентификации, вебхука о готовности, пакетного создания, идемпотентности по ключу клиента (повторный `POST /api/jobs` на тот же источник – новая задача и новая оплата), версионирования.

## Три варианта встраивания

**А. Сервис целиком в контуре.** Compose как есть, фронт как есть (`self-hosting.md`). Модели – свои через `*_BASE_URL` (раздел «Свои STT и LLM»), Turnstile `off` и фронт без публичного ключа, `YTDLP_PROXY`, если выход к платформам идёт через прокси. Обязательно добавить снаружи: аутентификацию перед nginx и доступ к результату по пользователю – сейчас ссылка на результат единственный ключ к нему.

**Б. Только движок.** Поднимаются `n8n` с флоу, `media`, `postgres`, `gotenberg` и внутренний nginx как точка входа `/api/`; фронт не нужен. Свой интерфейс ходит в четыре вызова раздела «API» (probe → jobs → статус опросом → экспорт) и строит страницу из JSON по `schemas/result.schema.json`. Turnstile `off`, лимиты nginx поднять под свой клиент, `MAX_CONCURRENT_JOBS` и бюджет – под свою очередь. Аутентификация и аудит целиком на стороне вашей системы.

**В. Вход только файлами.** Ваша система забирает запись из своего хранилища (сетевой каталог, S3) и отдаёт её в `POST /api/probe` multipart; сервис адреса хранилища не знает. Выход к видеоплатформам можно закрыть – ветки yt-dlp просто не вызываются, а probe по ссылке ответит ошибкой платформы. Модели и Turnstile – как в А; лимит файла (`UPLOAD_MAX_MB` и `client_max_body_size` в обоих nginx) и сроки хранения – под свои записи и свою политику.

## Конфигурация

Переменные читаются из `.env` через `env_file` всеми сервисами compose; n8n читает их в нодах через `$env`. Изменение `.env` действует после пересоздания контейнера, который переменную читает. Строки таблицы `settings` действуют со следующего запроса без перезапуска и главнее переменных.

| Переменная | По умолчанию | Кто читает | На что влияет |
|---|---|---|---|
| `DATA_DIR` | `/data` | media | каталог артефактов |
| `UPLOAD_MAX_MB` | 200 | media, `jobs-api` | потолок файла; ещё `client_max_body_size` в nginx |
| `RETENTION_HOURS` | 48 | media | удаление артефактов источников, к которым не обращались |
| `PLAYBACK_RETENTION_DAYS` | 30 | media | срок дорожки плеера у загрузок |
| `SOURCE_LOCK_WAIT_SEC` | 600 | media | ожидание второго запроса на тот же источник, затем 409 `source_busy` |
| `DIRECT_HEAD_TIMEOUT_SEC` | 15 | media | таймаут проверки прямых ссылок |
| `YTDLP_COOKIES_FILE`, `YTDLP_PROXY` | пусто | media | куки и прокси для yt-dlp |
| `AUDIO_FORMAT` | `wav` | media | формат рабочей дорожки |
| `API_KEY` | – | media | ключ `X-API-Key` медиа-сервиса |
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | `digest` / – / `digest` | postgres, учётка n8n | база |
| `MEDIA_URL` | `http://media:8000` | n8n | адрес медиа-сервиса |
| `MEDIA_API_KEY` | – | учётка n8n | совпадает с `API_KEY` |
| `N8N_API_KEY` | – | `n8n/scripts/*.sh`, `activate-image.sh` | public API n8n для импорта флоу и учёток |
| `STT_PROVIDER` | `openai` | `pipeline` | `deepgram`, `openai`, `groq` – встроенные адреса; иное – `STT_BASE_URL` |
| `STT_MODEL` | `whisper-1` | `pipeline`, `jobs-api` | модель STT и её цена для оценки бюджета |
| `STT_BASE_URL` | `http://localhost:8080/v1` | `pipeline` | свой OpenAI-совместимый STT |
| `STT_API_KEY` | – | учётка n8n «STT API» | ключ OpenAI-совместимого STT |
| `DEEPGRAM_API_KEY` | – | учётка n8n «Deepgram API» | ключ Deepgram; учётка нужна импорту при любом провайдере |
| `LLM_PROVIDER` | `openai` | `llm-call` | `openai`, `groq`, `openrouter` – встроенные адреса; иное – `LLM_BASE_URL` |
| `LLM_BASE_URL` | `http://localhost:8080/v1` | `llm-call` | свой OpenAI-совместимый chat-completions |
| `LLM_MODEL_MAP` | `gpt-4o-mini` | `llm-call` | модель для clean, map и большинства блоков |
| `LLM_MODEL_REDUCE` | `gpt-5.6-luna` | `llm-call` | модель для reduce и критики |
| `LLM_MODEL` | пусто | `llm-call` | запасное значение для обеих |
| `LLM_API_KEY` | – | учётка n8n «LLM API» | ключ LLM |
| `MAX_JOB_MINUTES` | 60 | `jobs-api`, `maintenance`; `settings` | таймаут задачи |
| `MAX_DURATION_SEC` | 5400 | `jobs-api`; `settings` | потолок длительности |
| `DAILY_BUDGET_USD` | 6.00 | `jobs-api`; `settings` | бюджет за скользящие 24 часа |
| `MAX_CONCURRENT_JOBS` | 2 | `jobs-api`; `settings` | задач в работе одновременно |
| `TURNSTILE_MODE` | `monitor` | `jobs-api`; `settings` | `off` / `monitor` / `enforce` |
| `TURNSTILE_SECRET` | – | учётка n8n «Turnstile» | секрет проверки токена |
| `TURNSTILE_HOSTNAMES` | домен эталонного экземпляра, `localhost`, `127.0.0.1` | `jobs-api` | принимаемые домены из ответа проверки – задать свой |
| `VITE_TURNSTILE_SITE_KEY` | – | сборка фронта (`deploy.sh`, `infra/web.Dockerfile`) | публичный ключ виджета; пусто – виджета нет |
| `RESULT_RETENTION_DAYS` | 30 | `maintenance` | хранение результата |
| `EVENTS_RETENTION_DAYS` | 7 | `log-events` | хранение событий |
| `EXECUTIONS_DATA_MAX_AGE`, `EXECUTIONS_DATA_PRUNE` | 168, `true` | n8n | хранение данных выполнений (в них транскрипты) |
| `GOTENBERG_URL` | `http://gotenberg:3000` | `jobs-api` | адрес PDF-сервиса |
| `PUBLIC_URL`, `SMTP_*` | – | `pipeline` | письма; интерфейс их не использует |

Переменные медиа-сервиса для нарезки, тишины, таймаутов и бинарников со значениями по умолчанию – `media-service/.env.example`.

**Модель по этапам.** `clean`, digest-map и все блоки, кроме критики, – `LLM_MODEL_MAP`; digest-reduce и `critique` – `LLM_MODEL_REDUCE`. Развести clean и map на разные модели без правки кода нельзя. Для новой модели – запись в `n8n/pricing.json` (`input_per_1m`, `output_per_1m`, при необходимости `supports_temperature: false`); без записи её стоимость считается нулём.

## Свои STT и LLM

**LLM.** `LLM_PROVIDER=local` (любое значение вне `openai`, `groq`, `openrouter`), `LLM_BASE_URL=http://<host>/v1`, ключ в `LLM_API_KEY` – уходит заголовком `Authorization: Bearer`. Запрос: `POST {base}/chat/completions` с `model`, `messages`, `response_format: {type: json_object}`, `temperature: 0.2` (если модель не помечена иначе в `pricing.json`), таймаут 300 с. Проверки ключа на старте для `local` нет.

**STT.** `STT_PROVIDER=local`, `STT_BASE_URL=http://<host>/v1`, ключ в `STT_API_KEY`. Запрос: `POST {base}/audio/transcriptions`, multipart `file` (mp3 куска до 10 минут), `model`, `response_format=verbose_json`, `timestamp_granularities[]=segment`, `language`; ожидаются `segments[]` с `start`, `end`, `text`, таймаут 600 с на кусок – сервер должен укладывать 10 минут аудио в 10 минут. Ветка Deepgram к своему серверу неприменима.

После смены ключа – `credentials.sh --only llm` или `--only stt` и повторный импорт флоу (`self-hosting.md`, «Первый запуск»).

**Что нужно от модели.** Размеры запросов по выполнениям на записях 52 и 1,4 минуты: clean – кусок до 1000 слов плюс 80 слов контекста и промпт, 1,4–3,7 тыс. токенов, ответ до 1,4 тыс.; map – кусок до 4000 слов, до 8,2 тыс.; reduce – 6,4 тыс. на 52 минутах, около 11 тыс. на 90; блоки получают весь очищенный транскрипт – 12,6 тыс. на 52 минутах, около 22 тыс. на 90. Контекст от 32 тыс. токенов закрывает все вызовы на предельной длительности. Ответ – строго JSON по схеме с таймкодами, скопированными из входа. Слабая модель: невалидный JSON или нарушение структуры – одна попытка исправления; затем на clean кусок чистится правилами без модели и задача идёт дальше с оговоркой, на map и reduce задача падает с `llm_failed`, на блоке блок пропускается.

**Что проверено прогонами:** Deepgram nova-3, OpenAI whisper-1, Groq whisper-large-v3 и turbo (отклонены: выпадали окна речи по 15–20 с), OpenAI gpt-4o-mini, gpt-4.1, gpt-5.6-luna. Только в коде, без прогона с настоящим сервером: `openrouter`, `STT_PROVIDER=local`, `LLM_PROVIDER=local` (ветка `local` проверялась на заглушке провайдеров `n8n/testing/provider-stub.json`).

## Безопасность

Есть: аккаунтов нет, ссылка на результат – единственный ключ (`j_` и 6 знаков из 36, перебор ограничен лимитом статуса); IP-адреса не хранятся – nginx без журнала запросов, адрес не уходит в n8n; медиа-сервис за `X-API-Key`; редактор и public API n8n только на loopback; учётки провайдеров в n8n, секреты в `.env`; тела ошибок клиенту нейтральные, подробности в таблице `events`; cookies и аналитики нет; шрифты локальные.

Нет – это добавляют при встраивании: аутентификация перед nginx (SSO/OIDC или basic auth на внешнем прокси), доступ к результату по пользователю, аудит доступа (выключен ради «IP не храним»; в корпоративном контуре решение обычно обратное), шифрование томов на диске, ротация ключей без ручного пересоздания учёток, ограничение исходящего трафика, заголовок CSP, регулярное резервное копирование.
