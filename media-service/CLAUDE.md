# media-service

Реализуй только этот сервис по `../docs/TZ-media-service.md`, порядок – п. 9 ТЗ.
Контекст системы – `../docs/contract-api.md`, но оркестрация, STT и LLM здесь НЕ живут.

- Python 3.12, FastAPI, pydantic v2, ruff, pytest.
- yt-dlp – standalone-бинарник в Dockerfile, не pip.
- subprocess с таймаутами, stderr в лог.
- Тесты без сети по умолчанию, сетевые – `@pytest.mark.network`.
