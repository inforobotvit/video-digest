# Video Digest – контракт фронт ↔ n8n ↔ Media Service

Версия 0.1. Дополняет `TZ-media-service.md` (что умеет медиа-сервис) и `result-schema.md` (что лежит в результате). Здесь – кто кого вызывает, в каком порядке, и как выглядит база.

## 1. Участники

| Кто | Где | Роль |
|---|---|---|
| Фронт | статика через nginx | форма, карточка, ожидание, результат |
| n8n `jobs-api` | n8n, вебхуки | публичный API для фронта, единственная точка входа |
| n8n `pipeline` | n8n, запуск по внутреннему вызову | сама обработка, обновляет статусы |
| Media Service | docker, FastAPI | probe, download, split, артефакты |
| Postgres | docker | таблица `jobs`, одна на всё |
| STT / LLM | внешние API или self-hosted | вызываются из `pipeline` |

Фронт не знает про Media Service. Все вызовы – через `jobs-api`. Между n8n и Media Service – заголовок `X-API-Key`.

## 2. Публичный API (фронт → n8n jobs-api)

Все пути под `/api/`. nginx проксирует `/api/` на n8n-вебхуки.

### POST /api/probe

Первый шаг, ещё не задача. n8n прозрачно проксирует в Media Service `/probe` или `/upload` и возвращает ответ фронту. Для файла – multipart, n8n пробрасывает как есть.

Ответ – см. `/probe` в ТЗ медиа-сервиса, плюс поле `estimate`:
```json
"estimate": {
  "seconds": 480,
  "strategy": "transcribe",
  "per_option": { "glossary": 15, "critique": 30, "self_check": 15, "action_items": 15, "decisions": 15, "questions": 15 }
}
```
Оценка: `seconds` – базовая обработка: субтитры – 60 сек фикс; транскрибация – `duration_sec * 0.08 + 60`. `per_option` – добавка в секундах на каждую опцию, фронт складывает выбранные с `seconds`. Константы по замерам прогонов 2026-09-06 (gpt-4o-mini на извлечение ~15 с, gpt-4.1 на critique ~30 с).

### GET /api/limits

Цифры лимитов для страницы (с 30 сентября, заход E4): до неё фронт печатал «до 4 часов» и «до 500 МБ» строками, пока сервер держал 90 минут и 200 МБ. Ответ `200 { "max_duration_sec": 5400, "upload_max_mb": 200 }`, `Cache-Control: no-store`. `max_duration_sec` – строка `settings` главнее переменной `MAX_DURATION_SEC`, как на `/api/probe` и создании; `upload_max_mb` – только переменная `UPLOAD_MAX_MB` (её читает nginx, строка в таблице показала бы число, которого nginx не соблюдает). Недоступная база – ответ по переменным. Фронт вызывает ручку один раз при открытии главной: строка под полем («до 200 МБ · до 90 минут»), текст `file_too_large` и проверка размера до отправки берут числа отсюда; пока ответа нет или он не пришёл, форма работает без чисел, проверка до отправки пропускается, отказ отдаёт сервер. nginx: своя зона `limits`, 10 в минуту с запасом 5 на адрес (один вызов на загрузку главной, запас на несколько перезагрузок подряд); проверено 30 сентября: шесть запросов подряд 200, седьмой 429. Недоступная база – не 500, а ответ по переменным, как на `/api/probe`: проверено переименованной таблицей `settings`.

### POST /api/jobs

Создаёт задачу.

```json
{
  "source_id": "a1b2c3",
  "source_language": "ru",
  "preset": "lecture",
  "output_language": "ru",
  "options": ["glossary", "critique"],
  "email": "user@example.com",
  "consent_152fz": true
}
```

Поле `turnstile_token` (с 29 сентября, необязательное): токен Cloudflare Turnstile с формы запуска, виджет один на обе формы (ссылка и файл), `action` = `create_job`; токен одноразовый, живёт пять минут, фронт сбрасывает виджет после каждой попытки. Проверка после бюджета и до вставки задачи: `POST https://challenges.cloudflare.com/turnstile/v0/siteverify` с `secret` (учётка n8n «Turnstile», custom auth, тело запроса) и `response`; `remoteip` не отправляется – адреса не обрабатываем. Принимается только `success = true`, `action = create_job` и `hostname` из `TURNSTILE_HOSTNAMES`. Повтор токена ловим сами: sha256 каждого проверенного токена лежит в `turnstile_used` (`infra/sql/005_turnstile_used.sql`) десять минут, второе предъявление – отказ с `error-codes=duplicate`; сам Cloudflare 28 сентября принял один токен трижды. Режим – строка `TURNSTILE_MODE` в `settings` с откатом на переменную окружения, умолчание `monitor`: `off` – ничего не проверяем, событий нет; `monitor` – задача создаётся всегда, нет токена – событие `turnstile_missing`, отказ siteverify или повтор – `turnstile_failed` с `error-codes`; `enforce` – нет токена, отказ или повтор – `403 bot_check_failed` с человеческим текстом и то же событие. Во всех режимах недоступный или не ответивший за 5 с siteverify – задача создаётся, событие `turnstile_unreachable`. В телах событий адресов нет; события созданной задачи несут её `job_id`. Ставка nginx на `POST /api/jobs` не меняется.

`preset` и `options` (с 30 сентября, заход E4): пресет задаёт умолчания галочек на форме и акцент промптов digest, блоков сам не добавляет; `options` – итоговый список блоков extras, который фронт собирает из умолчаний пресета плюс-минус правки человека. `preset: lecture, options: []` – лекция без глоссария и вопросов, так и задумано; до 30 сентября пайплайн объединял блоки пресета с `options`, и снять блок пресета было нельзя. Умолчания по пресетам – `result-schema.md`, раздел 6; `estimate_sec` считается по тому же `options`.

Правила: `email` необязателен; если есть – `consent_152fz` обязан быть `true`, иначе 400. `source_language` – то, что показали на карточке, с возможной правкой пользователя. При ручных субтитрах язык обязан быть одним из `subtitles.manual` (правило 1.1 схемы): `/api/probe` уже отдаёт `language` из manual, если язык метаданных туда не входит; если задачу всё же создали с другим языком, n8n подменяет его первым manual и пишет `meta.language_override`.

Ответ `202`:
```json
{ "job_id": "j_8f2k1", "status": "queued", "url": "/jobs/j_8f2k1" }
```

Дневной бюджет. До вставки строки n8n считает по таблице `jobs`: `потрачено` – за последние 24 часа по задачам, которые не выполняются, `coalesce(total_cost_usd, sum(meta.stages[].cost_usd))` (у упавших `total_cost_usd` нет, есть только стоимость оплаченных этапов); `зарезервировано` – `sum(meta.estimated_cost_usd)` по задачам в `queued`/`processing`, созданным не раньше чем `MAX_JOB_MINUTES` назад (зависшие в `processing` никто не закрывает, без окна они держали бы резерв вечно). Если `потрачено + зарезервировано + оценка новой > DAILY_BUDGET_USD` – ответ `429`, код `daily_limit`, задача не создаётся. Сам предел, как и `MAX_CONCURRENT_JOBS`, `MAX_DURATION_SEC`, `MAX_JOB_MINUTES`, берётся из таблицы `settings`, если там есть строка, иначе из переменной – в том же запросе `Load budget` (раздел 7). Порядок отказов на создании: `unknown_duration`, `too_long`, `daily_limit`, `busy`. Проверка и вставка – два запроса, два одновременных запроса могут пройти оба: перерасход не больше одной оценки задачи, принято. Одновременные задачи. Той же выборкой считается число задач в `queued`/`processing` в окне `MAX_JOB_MINUTES`; если их не меньше `MAX_CONCURRENT_JOBS` – ответ `429`, код `busy`. Лимит проверяется после бюджета: при исчерпанном бюджете «попробуйте через несколько минут» вводило бы в заблуждение. Порядок отказов на создании: `unknown_duration` → `too_long` → `daily_limit` → `busy`.

n8n: пишет строку в `jobs`, отвечает фронту (Respond to Webhook), затем вызывает `pipeline` через Execute Workflow с `job_id`. Ответ уходит до старта обработки.

### GET /api/jobs/{job_id}

Опрос статуса и получение результата. Одна ручка, ответ зависит от статуса.

```json
{
  "job_id": "j_8f2k1",
  "status": "processing",
  "created_at": "2026-09-07T10:00:00Z",
  "finished_at": null,
  "estimate_sec": 480,
  "preset": "lecture",
  "options": ["critique"],
  "email": "a.petrova@example.org",
  "stages": [
    { "name": "probe", "status": "done", "ms": 1800 },
    { "name": "download", "status": "done", "ms": 14000 },
    { "name": "transcribe", "status": "running", "progress": { "done": 3, "total": 7 } },
    { "name": "clean", "status": "pending" },
    { "name": "digest", "status": "pending" },
    { "name": "extras", "status": "pending" },
  ],
  "source": { "title": "...", "duration_sec": 3721, "thumbnail_url": "...", "platform": "youtube", "language": "ru", "url": "https://..." },
  "result": null,
  "error": null
}
```

Поля для страницы ожидания: `created_at` и `estimate_sec` (базовая оценка плюс `per_option` блоков из `options`, как считает фронт на форме) дают «осталось около N минут» и «чуть дольше обычного»; `stages[].ms` – длительность завершённых этапов; `preset`, `options`, `email` – строка карточки и «пришлём письмо на …». `finished_at` появляется при `done` и `failed`.

При `status: "done"` в `result` лежит полный JSON по `result-schema.md`. При `failed` – `error: { "stage": "download", "code": "bot_check", "message": "..." }`. Если `status: "done"`, а `result: null` – результат удалён по сроку хранения (п. 4), фронт показывает страницу «Результат удалён» с датой из `finished_at` и «Обработать заново» для задач со ссылкой.

Фронт опрашивает каждые 3 секунды, пока статус не `done` или `failed`. Заголовок `Cache-Control: no-store`.

### GET /api/jobs/{job_id}/export/{format}

`format`: `digest.md` | `transcript.md` | `transcript.srt` | `digest.html` | `digest.pdf` | `all.zip`. Оговорки из `result.notices` (сокращённый транскрипт, очистка без модели – раздел 2 схемы результата) печатаются цитатой с местами в `digest.md`, `digest.html`/`pdf` и `transcript.md`, тем же текстом, что на странице. Всё генерируется из `result` на лету: md, srt, html – в n8n, pdf – из html через Gotenberg (сервис в compose), zip – md + transcript.md + srt + html + pdf + `result.json`; в `result.json` поле `transcript.segments[].speaker` отдаётся как `null` (в данных API оно есть, см. схему п. 3): нумерация говорящих локальна для куска и атрибуцией не является. Кэша нет; если pdf на часовом видео окажется дольше 5 секунд, добавим кэш. Ошибки: 404 `not_found`, 400 `bad_format`, 410 `gone` (результат удалён по сроку хранения), 409 `not_ready`, пока задача не `done`. Ответ – файл с `Content-Disposition: attachment`.

### GET /api/jobs/{job_id}/media

Только для `playback.kind = audio`. n8n проверяет задачу и отвечает заголовком `X-Accel-Redirect: /media-internal/{source_id}/playback.mp3`, а nginx сам отдаёт файл из Media Service с честным `Range` (206, `Content-Range`), не поднимая его в память n8n. Для остальных видов воспроизведения ручка отвечает 404 `no_media` – фронт берёт `playback.url`.

### POST /api/feedback

Оценка со страницы результата (заход E2, 23 сентября), UMUX-Lite: два утверждения по пятибалльной шкале согласия и необязательный комментарий. Тело: `{ "job_id": "j_…", "fits": 1..5, "easy": 1..5, "comment": "до 500 знаков, необязательно", "via": "timer" | "button" }` – `fits` «Возможности сервиса соответствуют моим требованиям», `easy` «Сервисом легко пользоваться», `via` – как открыта форма. Ответ `201 { "ok": true, "job_id" }`. Отказы: `400 validation_error` (оценка не целое 1–5, комментарий длиннее 500, `via` не из двух); `404 not_found` – задачи нет; `409 not_ready` – задача не `done` (упавшую не оцениваем); `409 already_rated` – на задачу уже отвечали, один ответ на задачу, повтор не перезаписывает. Хранится в таблице `feedback` (`infra/sql/004_feedback.sql`): `job_id` (первичный ключ), `fits`, `easy`, `comment`, `via`, `created_at`; чистка по срокам её не касается. Лимит nginx: своя зона `feedback`, 3 в минуту с запасом 3 на адрес – один ответ на задачу, человек оценивает задачу-две в день, четвёртый быстрый запрос получает `429 rate_limited`. Поле комментария подписано «без персональных данных», почта для ответа не собирается. Чтение – только psql (deploy-guide, раздел дня поста).

### POST /api/jobs/{job_id}/retry

Для `failed` (и для `done` с удалённым результатом, если у задачи есть `source.url`). Создаёт новую задачу с теми же параметрами, отвечает `202` как `POST /api/jobs`. Старую не трогает. Источник в Media Service к этому моменту может быть удалён, поэтому `retry` сначала повторяет `/probe` по сохранённой ссылке; для загрузок без исходника отвечает `410 source_gone` – фронт предлагает загрузить файл заново.

## 3. Статусы

Задача:

```
queued → processing → done
                    → failed
```

Этап (`stages[].status`): `pending` → `running` → `done` | `failed` | `skipped`.

Правила:
- `extras` может быть `failed` при задаче `done`. Основной результат важнее дополнительного.
- `transcribe` = `skipped`, если взяли ручные субтитры.
- `failed` задачи – только при падении `probe`, `download`, `transcribe`, `clean` или `digest`. Всё, что после, не роняет задачу.
- Задача в `processing` дольше `MAX_JOB_MINUTES` (env, 60) помечается `failed` с `code: timeout` отдельным cron-флоу в n8n.

## 4. Таблица jobs

```sql
create table jobs (
  id              text primary key,            -- j_ + 6 символов
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now(),
  finished_at     timestamptz,

  status          text not null,               -- queued | processing | done | failed
  stages          jsonb not null,              -- массив как в GET /api/jobs
  error           jsonb,

  source_id       text not null,               -- id в Media Service
  source          jsonb not null,              -- блок source из result-schema
  source_language text not null,
  preset          text not null,
  output_language text not null,
  options         text[] not null default '{}',

  email           text,
  consent_152fz   boolean not null default false,
  email_sent_at   timestamptz,

  result          jsonb,                       -- полный JSON по result-schema, после done
  meta            jsonb,                       -- стоимости и токены по этапам
  total_cost_usd  numeric(8,4)
);

create index jobs_status_idx on jobs(status);
create index jobs_created_idx on jobs(created_at desc);
```

Пользователей нет, кредитов нет – когда появятся, добавятся `users` и `user_id`, эта таблица не меняется.

Вторая таблица – `events`, нефатальные события пайплайна (`infra/sql/002_events.sql`): то, чего не хранят ни `jobs.error` (только фатальное), ни данные выполнения n8n (один прогон). Поля: `ts`, `job_id`, `stage`, `type`, `level` (`info` | `warn` | `error`), `provider`, `model`, `http_status`, `body` – замаскированное тело до 300 символов. Типы: `provider_auth` на любом этапе; `key_check_ok`, `key_check_failed`, `key_check_skipped` с причиной в `body` (субтитры, нет дешёвого GET у провайдера, неубедительный ответ – таймаут, 5xx, обрыв); `stt_language_rejected` – провайдер отказал в языке (`body`: код языка и текст отказа), чтобы через месяц знать, какие языки приносят; `stt_empty_result` – транскрипт собран, но пуст (`body`: слова, минуты, слов в минуту, язык); `clean_retention_low` – кусок clean после повтора удержал меньше 90% предложений входа (`body`: кусок, доля, первые пропавшие предложения), текст принят укороченным; `source_busy` – Media Service отказал, источник занят другим запросом дольше границы ожидания; `extras_block_skipped`; `validator_retry` с текстом отклонения; `job_failed` (level error) – любая штатная остановка задачи: `stage`, `body` – код и исходный текст причины, замаскированный (с 21 сентября `jobs.error.message` нейтрален, подробность живёт здесь); `turnstile_missing`, `turnstile_failed` (с `error-codes` siteverify или `duplicate`), `turnstile_unreachable` (level warn, stage `create`, provider `cloudflare`) – проверка Turnstile на создании задачи (с 29 сентября), в `monitor` и `enforce`; `internal_error` (level error) – внутренний сбой jobs-api, тот, на который клиент получил 500, или исключение в ноде пайплайна, пойманное Error Workflow `on-error` (`body`: выполнение и узел): `stage` – ручка (`create`, `probe`, `status`, `retry`, `export`, `media`), `body` – имя узла и замаскированный текст ошибки по правилам `provider_auth`; клиенту эти подробности не уходят; `provider_retry` – транспортный повтор вызова провайдера (с 20 сентября): 429 без `insufficient_quota`, 500, 502, 503, 504 повторяются до трёх попыток суммарно с паузой 25 с или `Retry-After` провайдера, если он не больше 60 с; обрыв соединения и таймаут – один повтор; `body`: этап и кусок, номер попытки «attempt 2 of 3», код ответа и код ошибки провайдера, пауза и откуда она взята («default» или «retry-after»); 400, 401, 403 не повторяются, 402 Deepgram (`ASR_PAYMENT_REQUIRED`, кредит исчерпан) и 429 `insufficient_quota` OpenAI отдаются как `provider_auth`; наши 429 (`daily_limit`, `busy`) – ответ человеку, не ошибка провайдера, к повтору отношения не имеют; `schema_violation` – результат нарушает схему или правила 2 и 7 (`body`: число и перечень нарушений), пишет finalize перед `done`; `result_expired` – результат удалён по сроку хранения (`body`: дата завершения и срок) и `job_timeout` – задача закрыта по `MAX_JOB_MINUTES` (`body`: этап и время создания), оба пишет флоу `maintenance`. Пишет подворкфлоу `log-events`, который пайплайн вызывает без ожидания: сбой вставки глотается и задачу не роняет. Чистка на каждой вставке: строки старше `EVENTS_RETENTION_DAYS` удаляются, maintenance-флоу не нужен. Читается через psql, UI нет.

Ретеншн: задача живёт `RESULT_RETENTION_DAYS` (30) дней после `finished_at`, `done` и `failed` одинаково. Флоу `maintenance` (Schedule Trigger, раз в час) удаляет содержание и опознавательные поля: `result`; в `source` – `title`, `url`, `thumbnail_url`, `playback` (остаются `type`, `platform`, `duration_sec`, `language`); `source_id` становится `expired` (для загрузок это отпечаток содержимого); `meta.quality_warnings` и `dropped_quotes` внутри `meta.stages` (в них лежат куски транскрипта и цитаты); `error.message` у упавших (может цитировать ответ провайдера). Остаётся только то, что нужно статистике: длительность, платформа, тип, языки, пресет, опции, стоимость, этапы со статусами и моделями, токены, оценки, даты, у ошибки – этап и код; маркер – `meta.expired_at`. Источник в Media Service удаляется вместе с `playback.mp3`, в `events` пишется `result_expired`. `GET /api/jobs/{id}` отдаёт `done` с `result: null` и `source.title: null` (фронт показывает «Результат удалён», в «Моих задачах» остаётся название, сохранённое браузером при создании), экспорт отвечает 410 `gone`, повтор невозможен – ссылки больше нет. До 17 сентября переменная существовала, а очистки не было – результаты жили бессрочно. Тот же флоу закрывает зависшие задачи: `queued`/`processing` старше `MAX_JOB_MINUTES` становятся `failed` с ошибкой `{ stage: <этап, который шёл>, code: "timeout" }` и событием `job_timeout` – иначе человек смотрит на крутилку, пока не закроет вкладку (выполнение n8n гибнет с перезапуском контейнера или на необработанной ошибке, и статус в базе не меняется никогда). Сверка ключей учёток против `.env` – в тот же флоу, после поста. Артефакты в Media Service чистятся через 48 часов после `done`, кроме `playback.mp3` для загруженных файлов – он живёт столько же, сколько `result` (`PLAYBACK_RETENTION_DAYS`, по умолчанию = `RESULT_RETENTION_DAYS`).

## 5. Флоу `pipeline` по шагам

Каждый шаг: обновить `stages` в базе до `running` → сделать → обновить до `done` с `ms` и `cost_usd` в `meta`. Падение – `failed` на этапе, дальше по правилам п. 3.

1. **probe** – уже сделан, данные из `source`. Этап сразу `done`.
1а. **проверка ключей** – до скачивания, пока не потрачен ни один цент: `GET /models` к провайдеру LLM и, если будет транскрибация, к провайдеру STT через те же учётки n8n, что используют этапы (OpenAI и Groq – `/models`, Deepgram – `GET /v1/auth/token` через учётку «Deepgram API»; у провайдера без дешёвого аутентифицированного GET проверка пропускается). Явный 401 или 403 – задача `failed` с кодом `provider_auth` на этапе, который бы этим ключом пользовался (`clean` или `transcribe`). Таймаут, 5xx, обрыв сети, пустой ответ – задача идёт штатно, след только в данных выполнения: служебная проверка не становится жёсткой зависимостью старта. Ключ из `.env` в проверке не участвует, чтобы не попасть в данные выполнения.
2. **download** – по `recommended` из probe: `Media /download mode=subtitles_manual` или `mode=audio`. При `bot_check` – задача `failed` с кодом, фронт покажет «загрузите файл».
3. **transcribe** – если аудио: `Media /split` → для каждого чанка `GET /artifacts/...` → STT → сдвинуть таймкоды на `chunk.start` → склеить сегменты. Два провайдера-ветки в одном цикле: OpenAI-совместимые (`/audio/transcriptions`, multipart, `segments[]`, учётка «STT API») и Deepgram (`POST /v1/listen` бинарным телом, `model=nova-3`, `language` из `source_language` как есть, `diarize=true`, `punctuate=true`, `smart_format=false`, `utterances=true`; сегменты из `utterances[]`, `speaker` = `"<кусок>:<номер>"`, `model_actual` из `metadata.model_info`, учётка «Deepgram API»). Отказ Deepgram в языке (400 с `language` в тексте) – `stt_failed` с понятным сообщением и событие `stt_language_rejected`; автоперехода на `multi` нет, чтобы не менять качество молча. После склейки – проверка по результату для любого провайдера: меньше 20 слов на минуту записи (норма речи около 110) – `stt_failed` «transcript is empty …» и событие `stt_empty_result`, запись этапа в `meta.stages` сохраняет `cost_usd` и `minutes`, потому что минуты оплачены. Причина: язык, который провайдер формально принимает, но не умеет, возвращается как 200 с пустым транскриптом (nova-3, `language=el` на русской записи), и без проверки clean, digest и критика отработали бы на пустоте за деньги и отдали бы документ из ничего без единой ошибки. Порог грубый намеренно: ловим «ничего», не «мало». `progress.done/total` обновлять после каждого чанка; пока число чанков неизвестно (до `/split` и до нарезки на куски у `clean` и `digest`), поля `progress` в этапе нет, фронт показывает «подготовка», а не `0/0`. Если субтитры – `skipped`, сегменты берутся из `subs.*.json`. Язык: у whisper – из первого чанка, сверить с `source_language`, расхождение – в лог и в `meta`, не останавливать; у Deepgram детекта нет, `language_detected_by = request`.
4. **clean** – по кускам транскрипта (около 4000 слов), промпт чистки, выход `transcript.clean`.
5. **digest** – map по кускам `clean` → reduce в `tldr`, `key_points`, `structure`, `quotes`. Валидация по п. 9 схемы. Здесь же – `output_language`.
6. **extras** – по одному вызову на заказанный блок (список `options` как есть, пресет блоков не добавляет), последовательно; `critique` на `LLM_MODEL_REDUCE`, остальные на `LLM_MODEL_MAP`. Каждый блок – свой под-статус в `meta.stages[extras].blocks`; упавший блок пропускается, задача остаётся `done`, этап `failed` только если упали все.
7. **finalize** – собрать `result` и проверить его схемой (`schemas/result.schema.json`, встроена в ноду при сборке флоу) и правилами 2 и 7 схемы, мягко: нарушения идут в `meta.quality_warnings` (`stage: finalize`) и одним событием `schema_violation` с перечнем, задача всё равно `done` – человеку лучше документ с кривым таймкодом, чем ничего, нам лучше узнать из событий, чем от него; затем (в том числе `source.playback`: для ссылок – embed-URL платформы, для загрузок – `audio` с ссылкой на `/media`), посчитать `total_cost_usd`, статус `done`, `finished_at`. Сгенерировать pdf и zip. Если есть `email` – отправить письмо со ссылкой `/jobs/{id}` (тема «Выжимка готова: {title}», tldr, число тезисов и частей, «Результат хранится N дней, до {дата}»; SMTP из `SMTP_*`, в dev – MailHog из compose на `localhost:8025`), записать `email_sent_at`; сбой почты задачу не роняет. Вызвать `Media DELETE /sources/{source_id}?keep=playback` – удаляет всё, кроме mp3 для воспроизведения.

## 6. Ошибки для фронта

| code | этап | что показать |
|---|---|---|
| `unsupported_url` | probe | «Эту ссылку не понимаем. Поддерживаем YouTube, VK Видео, Rutube, прямые ссылки на файл» |
| `private_or_removed` | probe | «Видео недоступно: приватное или удалено» |
| `bot_check_failed` | создание | HTTP 403, «Не удалось подтвердить, что запрос из браузера. Обновите страницу и попробуйте снова» + retry, виджет сбрасывается. Только в режиме `enforce` Turnstile: нет токена, отказ siteverify, повтор токена или не тот `hostname`/`action` |
| `bot_check` | probe / download | «YouTube просит подтверждение. Скачайте видео и загрузите файлом» + кнопка загрузки |
| `unknown_duration` | probe, создание | «Не удалось определить длительность. Попробуйте другой источник или загрузите файл». Media Service отдаёт `duration_sec = 0`, когда извлечь длительность не удалось; без неё нельзя проверить ни потолок длительности, ни бюджет, поэтому отказ |
| `too_long` | probe, создание | «Максимум N минут. Обрежьте или выберите другое». N – из поля `max_duration_sec` в теле ошибки (`MAX_DURATION_SEC / 60`), не строка во фронте. Проверяется и на `POST /api/jobs`: источник регистрируется в Media Service даже когда `/api/probe` ответил `too_long` |
| `daily_limit` | создание | «Сегодня сервис исчерпал дневной лимит. Попробуйте завтра». HTTP 429, задача не создана; окно скользящее, 24 часа |
| `busy` | создание | «Сейчас обрабатываются другие задачи, попробуйте через несколько минут». HTTP 429, задача не создана |
| `source_busy` | download / transcribe | «Эта запись уже обрабатывается, попробуйте через несколько минут» + retry. Media Service ответил 409: другой запрос держит этот источник дольше `SOURCE_LOCK_WAIT_SEC` (600 с). Событие `source_busy` в `events` |
| `provider_auth` | transcribe / clean / digest / extras | «Сбой на нашей стороне, с вашей ссылкой всё в порядке. Попробуйте позже.» Без кнопки повтора. Провайдер ответил 401 или 403: ключ отозван или учётка n8n отстала от `.env`; в extras блок пропускается, задача остаётся `done`. Подробности в `jobs.error.message` и в данных выполнения n8n, ключи в них замаскированы; строка `[video-digest] provider_auth …` пишется через `console.log`, но в n8n 2.x с task runner она до stdout контейнера не доходит – долг на долговечный лог |
| `stt_failed` | transcribe | «Не удалось распознать речь. Попробуйте ещё раз» + retry. В `jobs.error.message` – причина словами: отказ провайдера в языке или пустой транскрипт с числом слов и минут |
| `llm_failed` | clean / digest | «Не удалось сделать выжимку. Попробуйте ещё раз» + retry |
| `timeout` | любой | «Обработка заняла слишком долго» + retry. Ставит флоу `maintenance`, когда задача старше `MAX_JOB_MINUTES` всё ещё в `queued`/`processing`; `stage` – этап, который шёл |
| `rate_limited` | любая ручка | HTTP 429 от nginx, «Слишком много запросов с вашего адреса. Подождите минуту» + retry. Лимит на адрес клиента, а не на сервис: `daily_limit` и `busy` считает n8n по таблице `jobs` для всех сразу, `rate_limited` считает nginx в памяти по IP (`infra/nginx.conf`, зоны по ручкам: создание 2 в минуту с запасом 3, probe 10 в минуту с запасом 5, статус 2 в секунду с запасом 30 – опрос страницы ожидания раз в 3 с на вкладку, экспорт 6 в минуту с запасом 6, лимиты 10 в минуту с запасом 5, `/media` без лимита запросов – плеер шлёт Range на каждую перемотку; не больше 3 одновременных загрузок и 20 соединений с адреса). Тело – контрактный JSON от nginx, в журнал отказ не пишется (адреса не храним). Заголовки `X-Real-IP` и `X-Forwarded-For` внутренний nginx в n8n не пробрасывает (с 30 сентября): модуль real_ip уже превратил адрес в `$remote_addr` для лимитов, а нода Webhook n8n сохраняет все заголовки запроса в данных выполнения – с заголовком адрес лежал бы там 7 дней |
| `file_too_large` | probe (загрузка) | «Файл слишком большой. Максимум N МБ». N – `upload_max_mb` из `GET /api/limits`, не строка во фронте; без ответа ручки – «Он больше, чем принимает сервис». `UPLOAD_MAX_MB = 200` по всей цепочке: проверка на фронте до отправки (по той же ручке), `client_max_body_size 200m` в обоих nginx (413 с контрактным JSON), медиа-сервис, лимит n8n на form-data (200 МБ по умолчанию) |
| `internal_error` | любая ручка, любой этап | Задача: «Не удалось обработать видео» (текст `generic` фронта), ставит Error Workflow `on-error`, когда нода пайплайна бросила исключение – задача найдена по `meta.execution_id`, закрыта за секунды, а не по `MAX_JOB_MINUTES`; событие `internal_error` с именем узла. Ручка: HTTP 500, «Не удалось запустить. Попробуйте ещё раз» (для запуска; на странице задачи – как сетевая ошибка). Внутренний сбой jobs-api до ответа: недоступна база (`Load budget`, `Load job…`), недоступен Media Service, исключение в коде. До 20 сентября n8n отвечал на такой сбой `200` с пустым телом и задачу не создавал; теперь у нод Postgres, HTTP и Code на путях ответа ошибочный выход ведёт в общий `Respond 500`, `message` – узел и текст сбоя без секретов. Проверено переименованной таблицей (`settings`, `jobs`) и остановленным Media Service на всех шести ручках |

Для `extras` ошибки не блокируют страницу: блок показывается с плашкой «не удалось собрать, попробовать снова» (ретрай одного блока – вторая итерация).

## 7. Конфигурация n8n (env)

```
MEDIA_URL=http://media:8000
MEDIA_API_KEY=...
DATABASE_URL=postgres://...
STT_PROVIDER=deepgram        # deepgram | openai | groq | local
STT_MODEL=nova-3             # Deepgram nova-3, 0.26 $/час, без выпадающих окон семейства Whisper (2026-09-16); whisper-1 у OpenAI 0.36 $/час – запасной; Groq whisper-large-v3 и turbo отклонены – цены в n8n/pricing.json
STT_API_KEY=...              # ключ OpenAI-совместимого STT (учётка n8n «STT API», Bearer)
DEEPGRAM_API_KEY=...         # ключ Deepgram (учётка n8n «Deepgram API», заголовок Token; scripts/credentials.sh --only deepgram)
LLM_PROVIDER=...
LLM_MODEL=...               # запасной вариант, если ниже не задано
LLM_MODEL_MAP=...           # clean и digest-map: дешёвая модель
LLM_MODEL_REDUCE=gpt-5.6-luna   # digest-reduce и critique: модель, которая держит правила; luna – 0.20/1.20 $ за 1M против 2.00/8.00 у gpt-4.1 и 500 000 TPM против 30 000 на Tier 1 (2026-09-16, до сравнения на luna)
MAX_JOB_MINUTES=60
MAX_DURATION_SEC=5400        # 90 минут: лекция или подкаст идут 60–90 минут, отказ на нормальном видео хуже, чем меньше задач в сутки
TURNSTILE_SECRET=...         # секрет виджета Cloudflare Turnstile – только в учётку n8n «Turnstile» через scripts/credentials.sh --only turnstile
TURNSTILE_HOSTNAMES=digest.inforobot.space,localhost   # hostname из ответа siteverify, которые принимаем
TURNSTILE_MODE=monitor       # off | monitor | enforce; строка TURNSTILE_MODE в settings главнее, крутится в день поста без перезапуска
DAILY_BUDGET_USD=6.00        # потолок расходов за скользящие 24 часа, см. POST /api/jobs
MAX_CONCURRENT_JOBS=2        # задач в queued/processing одновременно, см. POST /api/jobs
RESULT_RETENTION_DAYS=30
EVENTS_RETENTION_DAYS=7      # таблица events, чистка на вставке; события живут короче результатов
EXECUTIONS_DATA_MAX_AGE=168  # часы; данные выполнений n8n (входы и выходы этапов, транскрипты) живут 7 дней – короче любой видимой копии
PLAYBACK_RETENTION_DAYS=30
PUBLIC_URL=https://...       # для ссылок в письмах
SMTP_*                       # письма
```

Лимиты как данные (с 20 сентября, `infra/sql/003_settings.sql`). `DAILY_BUDGET_USD`, `MAX_CONCURRENT_JOBS`, `MAX_DURATION_SEC` и `MAX_JOB_MINUTES` n8n читает из окружения при старте, поэтому поднять лимит переменной – значит пересоздать контейнер, а пересоздание рвёт выполняющиеся задачи – ровно в день, когда бюджет кончился и идут люди. Таблица `settings (key, value, updated_at)`: строка с числовым `value` главнее переменной и действует со следующего запроса, без перезапуска; нет строки или значение не число – работает переменная. Чтение встроено в запросы, которые и так выполняются (`Load budget` на создании, `Load limits` на `/api/probe`, `Stuck jobs` в `maintenance`), отдельного обращения к базе нет. Изменение – одна команда:

```
insert into settings (key, value) values ('DAILY_BUDGET_USD', '20') on conflict (key) do update set value = excluded.value, updated_at = now();
delete from settings where key = 'DAILY_BUDGET_USD';   -- назад к переменной
```

Проверено 20 сентября без перезапуска контейнера: строка `0.01` – следующий `POST /api/jobs` отвечает `429 daily_limit` с новой суммой в сообщении; строка удалена – проверка проходит по переменной. `UPLOAD_MAX_MB` остаётся переменной: он про nginx. Строка `MAX_DURATION_SEC` видна и в `GET /api/limits` (проверено 30 сентября: 600 → 5400 после удаления строки).

Модели описаны в `n8n/pricing.json`: цены для `meta.stages` и признак `supports_temperature: false` для моделей, принимающих только температуру по умолчанию (gpt-5.6-luna отвечает 400 на `temperature: 0.2`); llm-call тогда не шлёт параметр, без признака шлёт 0.2 как раньше.

`jobs.error.message` (с 21 сентября) – нейтральная фраза по коду («speech recognition failed», «the provider refused our request», «internal error on our side»…), без имён нод, путей, адресов и текстов провайдера: поле публичное. Исходная причина – событие `job_failed`. Фронт текст не показывает, он берёт заголовок и текст по коду из своих строк.

`jobs.meta.tools` (с 21 сентября) – версии инструментов, которыми получен probe: `ytdlp`, `ejs`, `js_runtime`, `ffmpeg` из `GET /sources/{id}` медиа-сервиса, пишет `Build job row` при создании. Когда экстрактор сломается, по старым задачам можно отличить «сломался yt-dlp» от «сломались мы».

`jobs.meta.execution_id` (с 21 сентября) – id выполнения n8n пайплайна, ставится в `Init`. По нему Error Workflow находит задачу, а человек – выполнение по жалобе: `select meta->>'execution_id' from jobs where id = 'j_…'`, затем `/workflow/<id пайплайна>/executions/<execution_id>` в n8n.

Оценка стоимости задачи. При создании n8n считает ожидаемую стоимость по `duration_sec` из probe и `n8n/pricing.json` и пишет её в `jobs.meta.estimated_cost_usd`: STT – минуты × цена `STT_MODEL` (0 при ручных субтитрах; модели нет в `pricing.json` или файл не читается – берётся самая дорогая известная цена, 0.006 $/мин whisper-1: без прайса задачи всё равно принимаются, оценка лишь грубее), плюс LLM – `max(LLM_EST_MIN_USD, минуты × LLM_EST_USD_PER_MIN)`. Обе константы в коде рядом с расчётом: 0.0015 $/мин и планка 0.02 $ на задачу (2026-09-16, по фактам: 0.00043 $/мин с luna на reduce, 0.00124 с gpt-4.1 и критикой, 0.00076 у 72-минутного подкаста с переводом; пятиминутное видео с субтитрами стоило 0.0164, отсюда планка; 2026-09-17 после правила удержания clean – 0.00076 $/мин на Cosmoscow, константа остаётся). Константа станет зависимой от модели, когда моделей на reduce будет больше одной – долг. Промах оценки самоисправляется: оценка резервируется, только пока задача в `queued`/`processing`, у `done` в расход входит фактический `total_cost_usd`. 90 минут на whisper-1 – около 0.54 STT + 0.135 LLM ≈ 0.68 $, то есть около восьми максимальных задач в дневные 6 $.

Deepgram считается по прайсу `n8n/pricing.json` (0.00433 $/мин) и в `meta.stages`, и в оценке бюджета, хотя на период стартового кредита реальный расход ноль: при нулевой цене в день исчерпания кредита разом изменились бы и стоимость задачи, и вместимость дневного лимита. Цена в файле – всегда цена прайса, кредит – факт биллинга, а не свойство модели.

`STT_PROVIDER=local` переключает на self-hosted Whisper с OpenAI-совместимым API – меняется только base URL, флоу тот же. Это и есть «режим контура» для слайда.

## 8. Порядок реализации

1. Postgres + таблица, Media Service из ТЗ, `/api/probe` прозрачным прокси. Проверить карточку на реальных ссылках.
2. `POST /api/jobs` и `GET /api/jobs/{id}` с фейковым pipeline, который просто проходит этапы с задержками. На этом уже можно делать фронт ожидания.
3. Настоящий pipeline до `digest` включительно. Демо готово на этом шаге.
4. `extras`, экспорт, письмо.
5. `retry`, cron-таймаут, ретеншн. (`fact_check` снят 17 сентября: принимался, не выполнялся; вернётся только реализованным.)

Шаг 3 – точка, после которой сервис можно показывать. Всё после – улучшения, которые не должны сорвать дедлайн.
