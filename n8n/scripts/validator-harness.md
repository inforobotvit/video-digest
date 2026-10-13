# Харнесс валидатора

Проверяет изменения в валидаторе llm-call (`VALIDATE_JS` в `build_workflows.py`) на записанных ответах
моделей, без вызова модели и без оплаты транскрибации. Скрипт `Validate 1` берётся из
`workflows/llm-call.json`, состояние – из записанной ноды `Prepare`, ответ модели – из записанной
`LLM request 1`; `$('Prepare')` и `$input` подменяются заглушками, весь скрипт исполняется целиком –
в том порядке, в каком его исполняет n8n. Это ловит и ошибки правил, и ошибки порядка объявлений,
которые проверка синтаксиса не видит (17 сентября такая ошибка стоила прогона за 0.25 $).

```bash
scripts/fetch_executions.sh llm-call 40 > /tmp/llm-execs.json   # записанные вызовы, с данными
python3 scripts/build_workflows.py                               # собрать валидатор с правкой
node scripts/validator_harness.js /tmp/llm-execs.json clean       # прогнать только clean
node scripts/validator_harness.js /tmp/llm-execs.json --diff      # все виды, с вердиктом инстанса на тот момент
node scripts/validator_harness.js /tmp/llm-execs.json clean --attempt2   # вторая попытка: состояние из Retry, ответ из LLM request 2
```

Вывод – строка на ответ: id выполнения, метка (`clean 3/8`, `map 1/2`, `digest`), модель, вердикт
`ok` / `soft` / `hard` и текст ошибки; с `--diff` рядом показывается, что сказал инстанс, когда ответ
был записан, если вердикты разошлись. Внизу – счётчик.

Калибровочные записи для clean лежат в `fixtures/clean-calibration/` (пять прогонов 17 сентября: русская лекция, английский подкаст, субтитры VK, совещание, немецкое видео; обе попытки). Дамп одной задачи одной командой: `scripts/fetch_job_executions.sh <job_id> [kind] > файл` – окно по времени задачи из `job-status` плюс фильтр по названию видео в промпте (одновременные задачи делят окно); заголовки ответов вырезаются, ключевые формы и credential-значения `infra/.env` проверяются, при совпадении дамп не пишется. Сам измеритель – `scripts/clean_retention.js`: модуль для node и вставка в ноды при сборке.

## Отчёт удержания

`scripts/clean_retention_report.js` – калибровка правила 10 на тех же записях, без модели. Читает все файлы `fixtures/clean-calibration/` (или переданные) и печатает по каждому куску: язык, число единиц, удержание первой попытки старой и новой единицей, был ли повтор, сколько единиц вернуло исправление, «потеряно заново» старое и новое, класс (D дефектный, H честный, D*/H по чтению для кусков без повтора, ? спорный). Дальше: раздел A – потерянные единицы кусков без повтора полным текстом и их разметка (таблица `LABELS` в скрипте); B – длины потерянных единиц на английской записи и арифметика N; C – пороги по группам (общая, ru без VK, ru с VK, en) без правила длины, с ним и гибрид; контроль по всем записям; два признака починки. Старая реализация (до 20 сентября) держится копией внутри отчёта для колонок «старое» и в валидатор не возвращается.

```bash
node scripts/clean_retention_report.js                 # всё, пороги из clean_retention.js
node scripts/clean_retention_report.js --units         # плюс потерянные единицы каждого куска
node scripts/clean_retention_report.js --control=92    # что делает заданный порог на каждой записи
node scripts/clean_retention_report.js --n=15          # другое N для правила длины
node scripts/clean_retention_report.js --min=ru:5      # другой минимум содержательных слов для языка
```

Пороги в силе – `cleanThresholds()` в `scripts/clean_retention.js`, их читает и валидатор при сборке, и отчёт.

## Транспортный повтор: проверка заглушкой

`testing/provider-stub.json` – флоу-заглушка провайдеров в том же инстансе: `POST /webhook/stub/chat/completions` (OpenAI-совместимый чат) и `POST /webhook/stub/listen` (Deepgram), сценарий задаётся `POST /webhook/stub-control` `{"chat": [...], "listen": [...]}` – по одному ответу на вызов, дальше 200; записи `200`, `429`, `429:ra=5` (с `Retry-After`), `429:quota`, `402`, `400:language`, `500`, `503`. `GET /webhook/stub-control` отдаёт сценарий, счётчики и журнал вызовов с временем – по нему видны паузы. Флоу ничего не сохраняет (ноды шлют ему настоящие заголовки учёток) и в `workflows/` не экспортируется (`export.sh` его пропускает); в инстансе после проверки остаётся выключенным.

```bash
scripts/import.sh testing/provider-stub.json                                   # заглушка, активируется
python3 scripts/build_workflows.py --provider-stub http://localhost:5678/webhook/stub --out /tmp/stub
scripts/import.sh /tmp/stub/llm-call.json /tmp/stub/pipeline.json              # варианты с подменённым адресом
curl -s -X POST localhost:5678/webhook/stub-control -H 'content-type: application/json' -d '{"listen":["429","429","200","503"],"chat":["429:ra=5","200","500"]}'
# файл через /api/probe (21 минута синуса даёт три куска STT), затем POST /api/jobs; смотреть events и GET stub-control
scripts/import.sh workflows/llm-call.json workflows/pipeline.json               # вернуть настоящие флоу
scripts/export.sh && python3 scripts/build_workflows.py && git diff --stat     # diff должен быть пустым
curl -s -X POST "$N8N_URL/api/v1/workflows/<id заглушки>/deactivate" -H "X-N8N-API-KEY: $N8N_API_KEY"
```

Проверка Error Workflow тем же приёмом: `build_workflows.py --provider-stub URL --throw-after "<нода>" --out DIR` вставляет в вариант пайплайна Code-ноду `Boom` с исключением сразу после названной ноды; после `Download done` – задача должна стать `failed` с `internal_error` за секунды, после `Mark failed` – остаться как была (21 сентября, j_v0h9xd и j_25lv55).

Сами правила вердикта – `scripts/transport_retry.js`, модуль для node с теми же функциями, что вставляются в ноды; синтетические ответы (429 с `Retry-After`, `insufficient_quota`, 402, 400, 5xx, таймаут) гоняются одной командой `node -e` без инстанса.

Порядок при любом новом правиле: собрать, прогнать харнесс на записях, посмотреть, на каких ответах
оно срабатывает и с каким текстом, и только потом `import.sh`. Записи хранятся в инстансе столько,
сколько задано `EXECUTIONS_DATA_MAX_AGE` (по умолчанию две недели); ценные прогоны сохраняйте
файлом.

Это половина долга от 9 сентября «повтор задачи транскрибирует заново»: правки этапов после
транскрибации теперь проверяются без неё. Вторая половина – повтор самой задачи от сохранённого
транскрипта – остаётся.
