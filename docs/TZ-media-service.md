# ТЗ: Media Service для сервиса Video Digest

Версия 0.1 – черновик для Claude Code. Сервис – один из слоёв системы, отвечает только за работу с медиа. Оркестрация (n8n), STT и LLM живут снаружи и дёргают этот сервис по HTTP.

## 1. Зачем

Превращаем ссылку на видео или загруженный файл в готовое к транскрибации аудио. Сервис:

- определяет, что за источник и есть ли у него субтитры;
- если субтитры есть – отдаёт их в нормализованном виде, без скачивания видео;
- если нет – вытаскивает аудио, нормализует, режет на чанки под лимиты STT-провайдеров;
- хранит артефакты на диске и отдаёт их по id.

Сервис ничего не знает про Whisper, LLM и статусы задач. Это осознанно: его можно тестировать отдельно и переиспользовать.

## 2. Стек и ограничения

- Python 3.12, FastAPI, uvicorn.
- yt-dlp (официальный standалone-бинарник, не pip-версия – были проблемы с совместимостью), ffmpeg, ffprobe, Deno (JS-рантайм для JS-челленджей YouTube через EJS yt-dlp; без него yt-dlp с августа 2026 работает в устаревшем режиме без рантайма и предупреждает, что часть форматов недоступна; пин `DENO_VERSION` в Dockerfile, минимум 2.3.0 по документации yt-dlp, с 21 сентября).
- Docker, один контейнер. docker-compose с volume для артефактов.
- Без базы данных. Состояние – файлы на диске плюс `meta.json` в папке задачи.
- Логи в stdout, JSON-формат.
- Все внешние вызовы (yt-dlp, ffmpeg) через `subprocess` с таймаутами и захватом stderr в лог.
- Код: type hints, pydantic-модели для запросов и ответов, ruff, pytest.

## 3. API

Все ответы – JSON. Ошибки – `{"error": {"code": "...", "message": "..."}}` с адекватным HTTP-статусом. Все POST/DELETE требуют заголовок `X-API-Key` (см. п. 5), `GET /health` – без ключа.

### POST /probe

Проверяет источник, не скачивая тяжёлое.

Запрос:
```json
{ "url": "https://www.youtube.com/watch?v=..." }
```

Ответ:
```json
{
  "source_id": "a1b2c3",
  "platform": "youtube",
  "title": "...",
  "duration_sec": 3721,
  "subtitles": {
    "manual": ["ru", "en"],
    "auto": ["ru"]
  },
  "recommended": "subtitles_manual",
  "language": "en",
  "thumbnail_url": "https://i.ytimg.com/vi/.../hqdefault.jpg"
}
```

`language` – ISO 639-1 по правилу 1.1 `result-schema.md`: при ручных субтитрах – их язык (из нескольких – язык метаданных, если он среди них, иначе язык авто-дорожки `*-orig`, иначе первый), без ручных – поле `language` метаданных, иначе единственная авто-дорожка `*-orig`; может быть `null` – это первый шаг каскада из `result-schema.md` п. 1.1. `thumbnail_url` – превью для карточки, может быть `null`. `subtitles.auto` – только языки реальной речи (`*-orig`), авто-переводы YouTube не перечисляются.

`recommended` – одно из: `subtitles_manual`, `subtitles_auto`, `transcribe`. Логика: есть ручные сабы на нужном языке – берём их; есть только авто – помечаем и всё равно рекомендуем `transcribe` (авто-сабы YouTube на русском плохие); нет ничего – `transcribe`.

Ошибки: `unsupported_url` (400, сюда же плейлисты и каналы), `private_or_removed` (404), `bot_check` (403; YouTube попросил залогиниться или подтвердить возраст – важно отдавать отдельным кодом, чтобы фронт предложил загрузить файл), `ytdlp_failed` (502), `ytdlp_timeout` (504).

### POST /upload

Multipart-загрузка файла. Ограничение размера – через env `UPLOAD_MAX_MB`, по умолчанию 500. Допустимые расширения: mp4, mov, mkv, webm, mp3, m4a, wav, ogg, flac.

Ответ – как у `/probe`, но `platform: "upload"`, субтитры всегда пустые, `title` – имя файла без расширения. Файл хранится как `/data/{source_id}/source.{ext}`, повторная загрузка того же содержимого возвращает тот же `source_id`.

Ошибки: `unsupported_file` (400), `file_too_large` (413), `invalid_media` (400, ffprobe не смог прочитать), `no_audio` (400, нет аудиодорожки).

### POST /download

Скачивает то, что нужно для выбранной стратегии.

Запрос:
```json
{ "source_id": "a1b2c3", "mode": "subtitles_manual", "lang": "ru" }
```
или
```json
{ "source_id": "a1b2c3", "mode": "audio" }
```

Ответ для субтитров:
```json
{ "artifact": "subtitles", "path": "/data/a1b2c3/subs.ru.json", "segments": 842 }
```
Субтитры приводятся к единому формату независимо от исходного (vtt/srt/json3):
```json
[ { "start": 12.4, "end": 15.1, "text": "..." } ]
```

Ответ для аудио:
```json
{ "artifact": "audio", "path": "/data/a1b2c3/audio.wav", "duration_sec": 3721, "size_mb": 118.3 }
```
Аудио: моно, 16 кГц, wav (или mp3 с битрейтом из env, если нужно экономить место). Скачивать только аудиодорожку, не видео (`-f bestaudio`). Для файлов из `/upload` – просто извлечь дорожку через ffmpeg.

Для загрузок `/download` в режиме `audio` дополнительно делает `playback.mp3` для встроенного плеера (см. `result-schema.md` п. 1.2): стерео, если исходник был стерео, иначе моно; 44.1 кГц; 96 kbps. После этого исходный файл `source.*` удаляется – храним только нормализованные дорожки. В ответе для аудио появляется `"playback_path": "/data/a1b2c3/playback.mp3"` (для ссылок – `null`, плеер там платформенный).

Повторный `/download` с теми же параметрами возвращает уже готовый артефакт, не скачивая и не перекодируя заново.

Прямые ссылки на файл (`platform: generic`): yt-dlp длительности не отдаёт, поэтому сервис сам проходит редиректы (до пяти, каждый хоп проверяется), отказывает по `Content-Length` выше `UPLOAD_MAX_MB` (413 `file_too_large`) и читает заголовки контейнера через ffprobe по HTTP с `-rw_timeout` = `DIRECT_HEAD_TIMEOUT_SEC` (15 с); итоговый адрес хранится в `meta.download_url`, и скачивание идёт с него с `--max-filesize` = `UPLOAD_MAX_MB`. Защита от обращения по произвольному адресу (SSRF) применяется ко всем ссылкам до yt-dlp и на каждом редиректе: только `http` и `https`, имя разрешается, и любой адрес из loopback, приватных, link-local (включая 169.254.169.254), multicast, зарезервированных и shared диапазонов, а также `localhost`, `*.local`, `*.internal` – отказ 400 `unsupported_url` (`app/services/safe_url.py`, тесты `tests/test_safe_url.py` – условие выкладки). Проверка в коде не заменяет сетевую изоляцию: редиректы yt-dlp и перепривязку имени между проверкой и запросом она не видит, это закрывается только сетью контейнера (в очереди).

Ошибки: `subtitles_not_found` (404, нет дорожки на этом языке или у загрузки), `source_not_found` (404, нет такого `source_id`), `source_busy` (409, другой запрос обрабатывает этот источник дольше `SOURCE_LOCK_WAIT_SEC`, по умолчанию 600 с – повторить позже), `ffmpeg_failed` (500), `download_timeout` (504), плюс коды yt-dlp из `/probe`. Одновременные `/download` и `/split` на один `source_id` выполняются по очереди: второй ждёт первый и получает готовый артефакт.

### POST /split

Режет аудио на чанки под STT.

Запрос:
```json
{ "source_id": "a1b2c3", "chunk_sec": 600, "max_mb": 24 }
```

Ответ:
```json
{
  "chunks": [
    { "index": 0, "path": "/data/a1b2c3/chunks/000.mp3", "start": 0, "end": 600 },
    { "index": 1, "path": "/data/a1b2c3/chunks/001.mp3", "start": 600, "end": 1200 }
  ]
}
```

Важно: резать по тишине, а не строго по секундам. Использовать `silencedetect` ffmpeg, искать ближайшую паузу к границе чанка в окне плюс-минус 20 секунд. Иначе Whisper теряет слова на стыках. Каждый чанк несёт `start`, чтобы потом сдвинуть таймкоды транскрипта.

Как режем: `silencedetect` один раз на весь файл (порог `SILENCE_NOISE_DB`, минимум `SILENCE_MIN_SEC`); граница чанка – середина ближайшей к отметке паузы в окне `±SPLIT_WINDOW_SEC`, если паузы в окне нет – ровно по отметке, без ошибки. Хвост короче 1 с приклеивается к предыдущему чанку. Чанки идут встык: `end` предыдущего равен `start` следующего, `end` последнего равен длительности файла. `chunk_sec` и `max_mb` – по умолчанию из env; `max_mb` ограничивает длину чанка по битрейту (`CHUNK_BITRATE`), а после кодирования размер каждого файла проверяется.

Чанки – mp3, моно, 16 кГц, `CHUNK_BITRATE`. Рядом лежит `chunks/manifest.json` с параметрами и списком чанков: повторный `/split` с теми же параметрами возвращает его без перекодирования, с другими – перерезает заново.

Ошибки: `source_not_found` (404), `audio_not_found` (409, сначала `/download mode=audio`), `source_busy` (409, как у `/download`), `ffmpeg_failed` (500), `chunk_too_large` (500), `download_timeout` (504).

### GET /artifacts/{source_id}/{name}

Отдаёт файл (аудио-чанк, субтитры, `playback.mp3`). Нужен, чтобы n8n мог отправить чанк в STT и проксировать `playback.mp3` в `GET /api/jobs/{id}/media`. Для `playback.mp3` обязательна поддержка `Range`-запросов (206, `Accept-Ranges: bytes`), иначе перемотка в браузере не работает.

`name` – `subs.{lang}.json`, `audio.wav|mp3`, `playback.mp3`, `chunks/NNN.mp3`. Остальное (`meta.json`, `source.*`, `raw/`, `chunks/manifest.json`) наружу не отдаётся – 404 `not_found`. Без API-ключа, как и `/health`.

### GET /sources/{source_id}

Для оркестратора: чем был источник и что показал `/probe`. За `X-API-Key`, в отличие от остальных GET.

```json
{ "source_id": "a1b2c3", "kind": "url", "url": "https://...", "original_filename": null, "probe": { ...ответ /probe... } }
```

`kind` – `url` | `upload`; для загрузок `url: null`, `original_filename` – имя файла. Неизвестный id – 404 `source_not_found`.

### DELETE /sources/{source_id}

Удаляет папку задачи. Вызывается оркестратором после `done`. С параметром `?keep=playback` удаляет всё, кроме `playback.mp3` и `meta.json` – так оркестратор оставляет дорожку для встроенного плеера (если `playback.mp3` нет, как у ссылок, папка удаляется целиком). Ответ `{ "deleted": true, "source_id": "...", "kept": ["playback.mp3"] }`; для несуществующего `source_id` – 200 с `deleted: false`, чтобы повтор был безопасен.

Фоновая чистка: рабочие артефакты (`audio.*`, `chunks/`, `subs.*`, `source.*`, `raw/`) удаляются, если к источнику не обращались дольше `RETENTION_HOURS` (env, по умолчанию 48; возраст – самый свежий mtime в папке без учёта `playback.mp3`); `playback.mp3` – по своему mtime старше `PLAYBACK_RETENTION_DAYS` (env, по умолчанию 30). Папка удаляется, когда в ней не осталось артефактов. Цикл идёт раз в `RETENTION_SWEEP_MINUTES` (30; 0 выключает), первый прогон на старте.

### POST /maintenance/sweep

Запускает ту же чистку сейчас и возвращает отчёт: `{ "removed": [...], "sources_removed": [...], "checked": 6 }`. Для отладки и ручной уборки.

### GET /health

`{ "status": "ok", "ytdlp": "2026.xx.xx", "ffmpeg": "7.x", "ejs": "0.8.0", "js_runtime": "deno-2.9.7" }` – версии бинарников, чтобы видеть, что контейнер собран правильно; `ejs` – версия решателя JS-челленджей внутри yt-dlp, `js_runtime` – рантайм, который yt-dlp нашёл (`null` – не нашёл, YouTube в устаревшем режиме). Те же четыре версии отдаёт `GET /sources/{id}` полем `tools`, оркестратор пишет их в `jobs.meta.tools` при создании задачи.

## 4. Структура на диске

```
/data/
  {source_id}/
    meta.json          # результат probe + история операций
    source.mp4         # только для /upload, исходник; удаляется после /download audio
    subs.ru.json
    audio.wav          # моно 16 кГц, рабочая дорожка для STT
    playback.mp3       # только для /upload, дорожка для встроенного плеера, живёт дольше остальных
    chunks/
      manifest.json    # параметры /split и список чанков
      000.mp3
      001.mp3
```

`source_id` – 12 hex-символов. Для ссылок – `sha256("{extractor}:{id}")[:12]` по данным yt-dlp, поэтому разные формы одной ссылки (`youtu.be/X`, `watch?v=X`) дают один id. Для файлов – `sha256(содержимое)[:12]`. Повторный `/probe` того же видео возвращает тот же id и не скачивает заново, если артефакты уже есть.

## 5. Конфигурация (env)

```
DATA_DIR=/data
UPLOAD_MAX_MB=500
RETENTION_HOURS=48           # рабочие артефакты
PLAYBACK_RETENTION_DAYS=30   # playback.mp3 для загрузок
RETENTION_SWEEP_MINUTES=30   # период фоновой чистки, 0 – выключить
YTDLP_COOKIES_FILE=          # путь к cookies.txt, если YouTube блокирует
YTDLP_PROXY=                 # опционально
AUDIO_FORMAT=wav             # wav | mp3
AUDIO_MP3_BITRATE=64k        # битрейт для AUDIO_FORMAT=mp3
PLAYBACK_BITRATE=96k         # playback.mp3
CHUNK_SEC_DEFAULT=600
PROBE_TIMEOUT_SEC=90         # таймаут yt-dlp на /probe
DOWNLOAD_TIMEOUT_SEC=1800    # таймаут yt-dlp и ffmpeg на /download
FFPROBE_TIMEOUT_SEC=30
CHUNK_MAX_MB_DEFAULT=24
CHUNK_BITRATE=64k            # mp3 чанков для STT
SPLIT_WINDOW_SEC=20          # окно поиска паузы вокруг границы чанка
SILENCE_NOISE_DB=-30         # порог silencedetect
SILENCE_MIN_SEC=0.3          # минимальная длительность паузы
API_KEY=                     # ключ сервис-сервис, проверяется на всех POST/DELETE.
                             # Заголовок X-API-Key (основной) или Authorization: Bearer.
                             # Пустое значение = проверка выключена, только для dev.
```

## 6. Платформы

Первый релиз: YouTube, VK Видео, Rutube, прямые ссылки на mp4/mp3, загрузка файла. Всё через yt-dlp, отдельных клиентов не писать. `platform` в ответе `/probe` брать из `extractor` yt-dlp.

## 7. Тесты

- Unit: нормализация субтитров (vtt, srt, json3 → единый формат), поиск границ по тишине, генерация `source_id`.
- Integration: `/probe` и `/download` на коротком публичном видео с субтитрами и на локальном файле из `tests/fixtures/` (10-секундный wav). Сетевые тесты помечать `@pytest.mark.network`, чтобы CI мог их пропускать.
- Моки yt-dlp и ffmpeg для остальных тестов – сеть в CI не нужна.

## 8. Что НЕ входит

- Транскрибация и саммари – это n8n и внешние API.
- Статусы задач и очередь – это n8n и Postgres.
- Авторизация пользователей – нет, только `API_KEY` между сервисами.
- Извлечение слайдов из видео – отдельная фича на потом (есть готовый скрипт `extract-slides.sh`, можно перенести вторым этапом).

## 9. Порядок работы с Claude Code

1. Прочитать это ТЗ, задать вопросы, если что-то непонятно, до написания кода.
2. Каркас: структура проекта, pydantic-модели, `/health`, Dockerfile. Показать – приёмка.
3. `/probe` и `/upload`. Показать на реальной ссылке – приёмка.
4. `/download` с нормализацией субтитров. Приёмка.
5. `/split` с резкой по тишине. Приёмка.
6. `/artifacts`, `DELETE`, ретеншн, тесты, README с примерами curl.

Каждый шаг – отдельный коммит. Не идти дальше без приёмки.

## 10. Definition of Done

- `docker compose up` поднимает сервис, `/health` отвечает.
- Ссылка на YouTube с субтитрами: `/probe` → `/download` (subtitles) за секунды, без скачивания видео.
- Ссылка без субтитров: `/probe` → `/download` (audio) → `/split` даёт чанки не больше 24 МБ с корректными `start`.
- Загруженный mp4 проходит тот же путь, после `/download` есть `playback.mp3`, исходник удалён.
- Ошибка `bot_check` от YouTube отдаётся отдельным кодом, сервис не падает.
- Тесты зелёные без сети.
