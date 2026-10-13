# media-service

Медиа-слой Video Digest: ссылка или файл → нормализованные субтитры или аудио, нарезанное на чанки для STT. Оркестрация, распознавание и LLM живут снаружи (n8n) и дёргают этот сервис по HTTP. ТЗ и контракт: `../docs/TZ-media-service.md`, `../docs/contract-api.md`.

## Запуск

```bash
cp .env.example .env          # заполнить API_KEY
docker compose up -d --build  # сервис media, volume mediadata:/data, порт 8000
curl -s http://127.0.0.1:8000/health
# {"status":"ok","ytdlp":"2026.08.19","ffmpeg":"7.1.5-0+deb13u1"}
```

Образ: `python:3.12-slim-trixie`, ffmpeg 7.1 из apt, yt-dlp – standalone-бинарник с GitHub. Версия yt-dlp пинится через `ARG YTDLP_VERSION` (`docker compose build --build-arg YTDLP_VERSION=latest` для свежей). Swagger: `http://127.0.0.1:8000/docs`.

Все `POST` и `DELETE` требуют заголовок `X-API-Key` (или `Authorization: Bearer`), `GET /sources/{id}` тоже. `GET /health` и `GET /artifacts/...` – без ключа. Ошибки всегда в виде `{"error": {"code": "...", "message": "..."}}`.

## Полный путь на одной ссылке

Ниже – речь Стива Джобса в Стэнфорде (15 минут, есть ручные субтитры). Замените `change-me` на свой `API_KEY`.

```bash
BASE=http://127.0.0.1:8000
KEY='X-API-Key: change-me'
JSON='content-type: application/json'

# 1. Проверить источник (без скачивания)
curl -s -X POST $BASE/probe -H "$KEY" -H "$JSON" \
  -d '{"url":"https://www.youtube.com/watch?v=UF8uR6Z6KLc"}'
# {"source_id":"546439a993b7","platform":"youtube","title":"Steve Jobs' 2005 Stanford Commencement Address",
#  "duration_sec":904.0,"subtitles":{"manual":["ar","en","es","it","ja","km","pt"],"auto":["en"]},
#  "recommended":"subtitles_manual","language":"en","thumbnail_url":"https://i.ytimg.com/..."}

SID=546439a993b7

# 2a. Есть ручные субтитры – взять их (секунды, видео не скачивается)
curl -s -X POST $BASE/download -H "$KEY" -H "$JSON" \
  -d "{\"source_id\":\"$SID\",\"mode\":\"subtitles_manual\",\"lang\":\"en\"}"
# {"artifact":"subtitles","path":"/data/546439a993b7/subs.en.json","segments":244}
curl -s $BASE/artifacts/$SID/subs.en.json | head -c 300
# [{"start": 7.47, "end": 10.369, "text": "This program is brought to you by Stanford University."}, ...]

# 2b. Субтитров нет (recommended = transcribe) – скачать аудиодорожку
curl -s -X POST $BASE/download -H "$KEY" -H "$JSON" \
  -d "{\"source_id\":\"$SID\",\"mode\":\"audio\"}"
# {"artifact":"audio","path":"/data/546439a993b7/audio.wav","duration_sec":904.22,"size_mb":27.6,"playback_path":null}

# 3. Нарезать на чанки для STT (границы – по паузам в окне ±20 с)
curl -s -X POST $BASE/split -H "$KEY" -H "$JSON" \
  -d "{\"source_id\":\"$SID\",\"chunk_sec\":600,\"max_mb\":24}"
# {"chunks":[{"index":0,"path":"/data/546439a993b7/chunks/000.mp3","start":0.0,"end":599.797},
#            {"index":1,"path":"/data/546439a993b7/chunks/001.mp3","start":599.797,"end":904.22}]}

# 4. Забрать чанк для отправки в STT (таймкоды транскрипта сдвинуть на chunk.start)
curl -s -o chunk0.mp3 $BASE/artifacts/$SID/chunks/000.mp3

# 4b. Оркестратору: что это за источник и что показал probe (нужен ключ)
curl -s $BASE/sources/$SID -H "$KEY"
# {"source_id":"546439a993b7","kind":"url","url":"https://www.youtube.com/watch?v=UF8uR6Z6KLc",
#  "original_filename":null,"probe":{...как в ответе /probe...}}

# 5. Убрать за собой, когда результат готов
curl -s -X DELETE $BASE/sources/$SID -H "$KEY"
# {"deleted":true,"source_id":"546439a993b7","kept":[]}
```

## Загруженный файл

```bash
curl -s -X POST $BASE/upload -H "$KEY" -F "file=@lecture.mp4"
# {"source_id":"986432682780","platform":"upload","title":"lecture","duration_sec":3721.0,
#  "subtitles":{"manual":[],"auto":[]},"recommended":"transcribe","language":null,"thumbnail_url":null}

curl -s -X POST $BASE/download -H "$KEY" -H "$JSON" -d '{"source_id":"986432682780","mode":"audio"}'
# {"artifact":"audio","path":"/data/986432682780/audio.wav","duration_sec":3721.0,"size_mb":113.6,
#  "playback_path":"/data/986432682780/playback.mp3"}
```

Для загрузок `/download` дополнительно делает `playback.mp3` (44.1 кГц, 96 kbps, стерео, если было) для встроенного плеера и удаляет исходный файл. Плеер тянет дорожку с поддержкой перемотки:

```bash
curl -s -D - -o /dev/null -H "Range: bytes=0-1023" $BASE/artifacts/986432682780/playback.mp3
# HTTP/1.1 206 Partial Content
# content-range: bytes 0-1023/73185
# accept-ranges: bytes

# После done: удалить рабочие артефакты, оставить playback.mp3
curl -s -X DELETE "$BASE/sources/986432682780?keep=playback" -H "$KEY"
# {"deleted":true,"source_id":"986432682780","kept":["playback.mp3"]}
```

## Ретеншн

Фоновый цикл раз в `RETENTION_SWEEP_MINUTES` удаляет рабочие артефакты источников, к которым не обращались дольше `RETENTION_HOURS`, и `playback.mp3` старше `PLAYBACK_RETENTION_DAYS`. Пустые папки удаляются. Запустить вручную и посмотреть отчёт:

```bash
curl -s -X POST $BASE/maintenance/sweep -H "$KEY"
# {"removed":["/data/ec4441cdcb0c/audio.wav", ...],"sources_removed":["ec4441cdcb0c"],"checked":6}
```

## Коды ошибок

| code | HTTP | где | что значит |
|---|---|---|---|
| `unauthorized` | 401 | POST/DELETE | нет или неверный `X-API-Key` |
| `validation_error` | 422 | любой | тело запроса не по схеме |
| `unsupported_url` | 400 | probe | не видео, плейлист, канал, мёртвая страница |
| `private_or_removed` | 404 | probe, download | приватное, удалённое, с ограниченным доступом |
| `bot_check` | 403 | probe, download | YouTube просит войти или подтвердить возраст – предложить загрузку файла |
| `ytdlp_failed` / `ytdlp_timeout` | 502 / 504 | probe, download | yt-dlp упал или не уложился в таймаут |
| `unsupported_file` / `file_too_large` | 400 / 413 | upload | расширение не из списка, больше `UPLOAD_MAX_MB` |
| `invalid_media` / `no_audio` | 400 | upload | ffprobe не прочитал файл, нет аудиодорожки |
| `source_not_found` | 404 / 410 | download, split, artifacts | нет такого `source_id`; 410 – исходник загрузки уже удалён |
| `subtitles_not_found` | 404 | download | нет дорожки на этом языке, или это загрузка |
| `audio_not_found` | 409 | split | сначала `/download mode=audio` |
| `source_busy` | 409 | download, split | другой запрос обрабатывает этот источник дольше `SOURCE_LOCK_WAIT_SEC` (600 с); повторить позже |
| `ffmpeg_failed` / `chunk_too_large` / `download_timeout` | 500 / 500 / 504 | download, split | сбои перекодирования |
| `not_found` | 404 | artifacts | файла нет или его нельзя отдавать (`meta.json`, `source.*`, `raw/`) |

## Одновременные запросы на один источник

`/download` и `/split` берут блокировку на `source_id` (`flock` на `/data/.tmp/locks/<id>.lock`): второй запрос на тот же источник ждёт первый и получает готовый артефакт, а не делает работу заново и не переписывает файлы, которые первый уже забирает. Две задачи на одну ссылку в одну минуту – штатный случай (`MAX_CONCURRENT_JOBS = 2`), до 17 сентября он давал 500 на переименовании общего временного файла. Ожидание ограничено `SOURCE_LOCK_WAIT_SEC` (600 с, около двух худших случаев для 90-минутного видео и заведомо меньше 30-минутного таймаута оркестратора): дольше – 409 `source_busy`, чтобы залипший запрос не держал источник вечно, а второй не висел на соединении до обрыва.

## Конфигурация

Все переменные и значения по умолчанию – в `.env.example`, описание – в ТЗ, п. 5. Главные: `DATA_DIR`, `API_KEY`, `UPLOAD_MAX_MB`, `RETENTION_HOURS`, `PLAYBACK_RETENTION_DAYS`, `AUDIO_FORMAT` (`wav` | `mp3`), `CHUNK_SEC_DEFAULT`, `CHUNK_MAX_MB_DEFAULT`, `SOURCE_LOCK_WAIT_SEC`, `DIRECT_HEAD_TIMEOUT_SEC` (прямые ссылки: проверка редиректов и ffprobe по HTTP), `YTDLP_COOKIES_FILE` и `YTDLP_PROXY`, если YouTube блокирует.

Ссылки проверяются до любого обращения к ним (`app/services/safe_url.py`): только http и https, только публичные адреса – localhost, 127.0.0.0/8, 10/8, 172.16/12, 192.168/16, 169.254/16, ::1, fc00::/7 и прочие служебные диапазоны отклоняются с 400 `unsupported_url`, то же на каждом редиректе прямой ссылки.

## Разработка

```bash
uv sync                       # Python 3.12, зависимости и dev-группа
uv run pytest                 # без сети; тесты с реальным ffmpeg пропускаются, если его нет
uv run pytest -m network      # сетевые тесты, если появятся
uv run ruff check . && uv run ruff format --check .
uv run uvicorn app.main:app --reload --port 8000
```

Структура: `app/api/` – роуты, `app/services/` – yt-dlp, ffmpeg, парсеры субтитров, нарезка, ретеншн, `app/models.py` – схемы запросов и ответов, `tests/fixtures/` – 10-секундный wav.
