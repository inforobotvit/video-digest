# Свой экземпляр

Как поднять Video Digest на своём сервере: один хост, Docker Compose, образы собираются на этом же хосте из коммита репозитория. Локальный запуск для разработки – в `README.md`, встраивание в чужую систему и свои модели – в `integration.md`.

## Требования

- Linux-хост x86_64 или arm64 с Docker и Compose v2. Ориентир по ресурсам: 2 vCPU, 4 ГБ RAM, 30 ГБ диска. Образы занимают около 7 ГБ (n8n и Gotenberg по 2,5 ГБ, медиа-сервис 1,2 ГБ), каждый следующий релиз добавляет свои образы медиа-сервиса и фронта. Две задачи параллельно держатся на двух ядрах; пик нагрузки – ffmpeg и yt-dlp на скачивании.
- Ключи провайдеров: STT (Deepgram или OpenAI-совместимый `/audio/transcriptions`) и LLM (OpenAI-совместимый `/chat/completions`). Можно свои серверы – `integration.md`, раздел «Свои STT и LLM».
- Выход в интернет к видеоплатформам, если нужны ссылки. Без него сервис работает только с загруженными файлами.
- Обратный прокси с TLS перед сервисом (раздел «Обратный прокси»).
- Git на хосте: релиз собирается из `git archive` точного коммита.

## Каталог на хосте

Всё живёт в одном каталоге – корне приложения: по умолчанию `/opt/video-digest`, другой путь – переменная `APP_ROOT` при каждом запуске скриптов. Ниже корень обозначен `$APP_ROOT`.

```
$APP_ROOT/
  .env                    переменные, chmod 600
  repo/                   клон репозитория, только для git fetch и git archive
  releases/<SHA>/         снимок коммита: compose, промпты, SQL, исходники образов
  deploy.sh               копия infra/deploy/deploy.sh
  activate-image.sh       копия infra/deploy/activate-image.sh
  current.env             какой коммит запущен, пишет activate-image.sh
  n8n-credentials.json    карта «имя учётки → id» в n8n
```

Пример с другим корнем: `APP_ROOT=/srv/digest /srv/digest/deploy.sh <SHA>`. Запускать их может любой пользователь с доступом к Docker; отдельный пользователь без root – правильный выбор, членство в группе `docker` и так даёт ему почти root на хосте.

## Переменные: `.env`

Шаблон – `infra/.env.example`, копия ложится в `$APP_ROOT/.env`. Все сервисы compose читают его целиком через `env_file`, n8n – в нодах через `$env`. Обязательные:

| Переменная | Что это |
|---|---|
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | база; пароль – свой, не `change-me` |
| `API_KEY` и `MEDIA_API_KEY` | ключ медиа-сервиса: первый проверяет сам сервис, второй уходит в учётку n8n; значения должны совпадать |
| `N8N_API_KEY` | ключ public API n8n, появляется после первого запуска (раздел «Первый запуск»); без него флоу не импортируются |
| `STT_PROVIDER`, `STT_MODEL` | `deepgram` + `nova-3`, или `openai` + `whisper-1`, или свой сервер |
| `DEEPGRAM_API_KEY` или `STT_API_KEY` | ключ выбранного STT: Deepgram – первый, OpenAI-совместимые – второй |
| `LLM_PROVIDER`, `LLM_MODEL_MAP`, `LLM_MODEL_REDUCE`, `LLM_API_KEY` | провайдер (пусто – `openai`), дешёвая модель для чистки, map и большинства блоков, модель для reduce и критики, ключ |
| `TURNSTILE_HOSTNAMES` | ваш домен, если включаете Turnstile |
| `VITE_TURNSTILE_SITE_KEY` | публичный ключ виджета Turnstile; читает `deploy.sh` при сборке фронта |

Остальное имеет рабочие значения по умолчанию: лимиты (`MAX_DURATION_SEC`, `DAILY_BUDGET_USD`, `MAX_CONCURRENT_JOBS`, `MAX_JOB_MINUTES`), сроки хранения (`RESULT_RETENTION_DAYS`, `EVENTS_RETENTION_DAYS`, `RETENTION_HOURS`, `PLAYBACK_RETENTION_DAYS`, `EXECUTIONS_DATA_MAX_AGE`), адреса внутренних сервисов (`MEDIA_URL`, `GOTENBERG_URL`). Почта (`SMTP_*`, `PUBLIC_URL`) интерфейсом не используется. Полная таблица с тем, кто читает каждую переменную, – `integration.md`, раздел «Конфигурация».

Изменение `.env` действует после пересоздания контейнеров: следующий `activate-image.sh` пересоздаст все сервисы с `env_file`. Задачи, которые в этот момент шли в n8n, обрываются; их закроет `maintenance` как `timeout`.

## Compose

Рабочий compose – `infra/deploy/compose.server.yml`, он берётся из релиза, который запускается. Пять сервисов: `web` (nginx с собранным фронтом), `n8n`, `media`, `postgres`, `gotenberg`. Наружу на `0.0.0.0` не открыто ничего:

- `web` – `127.0.0.1:8080`, сюда смотрит обратный прокси;
- редактор и public API n8n – `127.0.0.1:5679`, только с самого хоста или через ssh-туннель `ssh -L 5679:127.0.0.1:5679 <хост>`.

Compose ждёт три переменные, их подставляет `activate-image.sh`: `MEDIA_IMAGE` и `WEB_IMAGE` (образы с тегом SHA коммита) и `RELEASE_DIR` (снимок коммита: оттуда n8n монтирует промпты и `pricing.json`, Postgres – SQL первого запуска). `infra/docker-compose.yml` – вариант для разработки, с открытыми портами и почтовым ящиком MailHog; на сервер он не годится.

## Первый запуск

1. Каталог и клон: `mkdir -p $APP_ROOT/releases && git clone <адрес репозитория> $APP_ROOT/repo`. Для приватного форка – отдельный deploy key только на чтение.
2. Скрипты: скопировать `repo/infra/deploy/deploy.sh` и `activate-image.sh` в `$APP_ROOT`, `chmod +x`.
3. `.env` по разделу выше, `chmod 600`. `N8N_API_KEY` пока пустой.
4. Первый релиз: `$APP_ROOT/deploy.sh <полный SHA коммита из main>`. Скрипт снимет `git archive`, соберёт оба образа, поднимет стек и ждёт, пока контейнеры станут здоровыми. Postgres на пустом томе сам применит `infra/sql/001–005`. Импорт флоу на первом запуске пропускается с предупреждением – ключа n8n ещё нет.
5. Владелец n8n: через туннель открыть `http://127.0.0.1:5679`, создать учётную запись владельца, затем Settings → n8n API → создать ключ и вписать его в `N8N_API_KEY` в `.env`.
6. Учётки провайдеров в n8n – из значений `.env`:
   ```bash
   cd $APP_ROOT/releases/<SHA>
   ENV_FILE=$APP_ROOT/.env N8N_URL=http://127.0.0.1:5679 bash n8n/scripts/credentials.sh
   cp n8n/.credentials.json $APP_ROOT/n8n-credentials.json
   ```
   Скрипт создаёт все семь учёток: Postgres, Media Service API, STT API, LLM API, Deepgram API, SMTP, Turnstile. Учётки с пустыми ключами тоже нужны – импорт флоу ищет их по имени.
7. Флоу: `$APP_ROOT/activate-image.sh <тот же SHA>` – поднимет стек заново и импортирует все шесть флоу из релиза, `maintenance` включится по расписанию раз в час.
8. Проверка: `curl -s http://127.0.0.1:8080/health` отвечает JSON с версиями yt-dlp и ffmpeg; `curl -s http://127.0.0.1:8080/api/limits` – лимиты; одна короткая задача через интерфейс доходит до `done`.

Смена ключа провайдера позже: исправить `.env`, затем `credentials.sh --only <postgres|media|stt|llm|deepgram|smtp|turnstile>`, скопировать карту обратно в `$APP_ROOT/n8n-credentials.json` и повторить `activate-image.sh` с текущим SHA – флоу подхватят новый id учётки.

## Turnstile

Проверка браузера Cloudflare Turnstile защищает форму запуска от роботов. Она необязательна. Режим – переменная `TURNSTILE_MODE` или строка `settings` с тем же ключом (строка главнее и действует без перезапуска):

- `off` – токен не проверяется, событий нет;
- `monitor` – токен проверяется, результат пишется событием в `events`, задача принимается в любом случае;
- `enforce` – задача без действующего токена получает `403 bot_check_failed`.

С Turnstile: создать виджет в панели Cloudflare на свой домен, публичный ключ – в `VITE_TURNSTILE_SITE_KEY` (вшивается в фронт при сборке), секрет – в `TURNSTILE_SECRET` и `credentials.sh --only turnstile`, домен – в `TURNSTILE_HOSTNAMES`. Начинать разумно с `monitor`, смотреть события `turnstile_*` и потом переходить на `enforce`.

Без Turnstile: `TURNSTILE_MODE=off` и фронт без публичного ключа – виджета на странице нет, браузер к Cloudflare не обращается. `deploy.sh` отказывается собирать фронт без ключа, чтобы виджет не пропал по ошибке; без Turnstile образы собирают вручную (раздел «Обновление и откат») с пустым `VITE_TURNSTILE_SITE_KEY` и поднимают `activate-image.sh`. Защита тогда держится на лимитах nginx по адресу, дневном бюджете и очереди.

## Бюджет и `settings`

Задача не создаётся, если вместе с уже потраченным за скользящие 24 часа и резервом работающих задач превысит `DAILY_BUDGET_USD` (`429 daily_limit`), или если в работе уже `MAX_CONCURRENT_JOBS` задач (`429 busy`). Оценка стоимости – по `n8n/pricing.json`; для новой модели туда добавляют цены, иначе её LLM-часть считается нулём.

Пять ключей меняются строкой в таблице `settings`, без перезапуска, и главнее переменных: `DAILY_BUDGET_USD`, `MAX_CONCURRENT_JOBS`, `MAX_DURATION_SEC`, `MAX_JOB_MINUTES`, `TURNSTILE_MODE`.

```bash
docker compose -p video-digest exec -T postgres sh -c 'psql -U $POSTGRES_USER -d $POSTGRES_DB' <<'SQL'
insert into settings (key, value) values ('DAILY_BUDGET_USD', '20')
  on conflict (key) do update set value = excluded.value, updated_at = now();
SQL
```

`delete from settings where key = '…'` возвращает значение переменной. Нечисловое значение у числового ключа игнорируется. Лимит файла `UPLOAD_MAX_MB` строкой не задаётся: его держат и медиа-сервис, и `client_max_body_size` в `infra/nginx.conf` и в обратном прокси.

## Хранение и чистка

| Данные | Где | Срок | Кто удаляет |
|---|---|---|---|
| загруженный исходный файл | том `mediadata` | до извлечения аудио, секунды | медиа-сервис |
| рабочее аудио и куски | том `mediadata` | до конца успешной задачи; у упавшей – до `RETENTION_HOURS` (48 ч) | пайплайн; цикл медиа-сервиса раз в 30 минут |
| дорожка плеера у загрузок | том `mediadata` | `PLAYBACK_RETENTION_DAYS` (30 дней) | медиа-сервис; `maintenance` вместе с результатом |
| результат, название, ссылка, обложка | таблица `jobs` | `RESULT_RETENTION_DAYS` (30 дней) после окончания | `maintenance` раз в час; остаются цифры без содержания |
| события | таблица `events` | `EVENTS_RETENTION_DAYS` (7 дней) | чистка на каждой вставке |
| данные выполнений n8n (входы и выходы нод, транскрипты) | том `n8ndata` | `EXECUTIONS_DATA_MAX_AGE` (168 ч) | n8n |
| оценки | таблица `feedback` | без срока | – |
| хэши токенов Turnstile | таблица `turnstile_used` | 10 минут | чистка на вставке |

Регулярного резервного копирования в сервисе нет. Перед обновлением с новыми SQL-файлами – дамп базы: `docker compose -p video-digest exec -T postgres sh -c 'pg_dump -U $POSTGRES_USER $POSTGRES_DB' > jobs.sql`. В томе n8n лежат учётки провайдеров, зашифрованные ключом самого n8n; том терять нельзя, иначе учётки создаются заново. В копиях – транскрипты и результаты, то есть то, что политика обещает удалять по сроку: копию держат не дольше, чем она нужна.

## Обратный прокси

Внутренний nginx в контейнере `web` слушает `127.0.0.1:8080` и ждёт перед собой прокси, который:

- терминирует TLS для вашего домена и отдаёт всё на `http://127.0.0.1:8080`;
- передаёт адрес клиента заголовком `X-Real-IP` – по нему внутренний nginx считает лимиты; без заголовка все посетители попадут в один лимит;
- пропускает тело до 200 МБ и ждёт загрузку не меньше двух минут (`client_max_body_size 200m`, `client_body_timeout 120s` в терминах nginx);
- не пишет журнал запросов, если вы сохраняете в политике обещание «IP-адреса не хранятся».

Подойдёт любой прокси: nginx, Caddy, Traefik, балансировщик облака. Пример для nginx на хосте – `infra/deploy/nginx-site.conf`, в нём заменить `server_name`.

## Обновление и откат

Обновление – новый коммит из `main`:

```bash
$APP_ROOT/deploy.sh <полный SHA>
```

`deploy.sh` обновляет клон, проверяет, что коммит лежит в `origin/main`, снимает его в `releases/<SHA>`, собирает `video-digest-media:<SHA>` и `video-digest-web:<SHA>` и передаёт `activate-image.sh`. Тот поднимает стек с новыми образами и ждёт здоровья контейнеров; если новый релиз не поднялся, сам возвращает прошлый. После удачного запуска он записывает `current.env` и импортирует флоу этого релиза.

Вручную, например без Turnstile, то же самое:

```bash
R=$APP_ROOT/releases/<SHA>
mkdir -p $R && git -C $APP_ROOT/repo archive <SHA> | tar -x -C $R
docker build -t video-digest-media:<SHA> $R/media-service
docker build -t video-digest-web:<SHA> -f $R/infra/web.Dockerfile --build-arg VITE_TURNSTILE_SITE_KEY= $R
$APP_ROOT/activate-image.sh <SHA>
```

Откат – запуск прошлого коммита теми образами, что уже лежат на хосте: `$APP_ROOT/activate-image.sh <прошлый SHA>` (прошлый SHA – в `current.env` до обновления или в `docker image ls video-digest-web`). Поэтому старые образы не чистят `docker image prune -a`, а удаляют поштучно, оставляя несколько последних релизов.

Чего выкат не делает сам:

- новые файлы `infra/sql/*.sql` на существующей базе применяются руками через `psql`, до импорта флоу, которым они нужны; все файлы идемпотентны;
- откат не откатывает данные: таблицы и строки, добавленные новым релизом, остаются;
- копии скриптов в `$APP_ROOT` обновляются руками, если изменились `infra/deploy/deploy.sh` или `activate-image.sh`.
