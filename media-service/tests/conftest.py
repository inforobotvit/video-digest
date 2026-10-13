from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.services import binaries


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    # _env_file=None: ignore a developer's local .env, keep tests hermetic.
    return Settings(_env_file=None, data_dir=tmp_path / "data", api_key="test-key")


@pytest.fixture
def fake_binaries(monkeypatch: pytest.MonkeyPatch) -> None:
    # No subprocess calls in unit tests: pretend both binaries are present.
    monkeypatch.setattr(binaries, "ytdlp_version", lambda _bin: "2026.08.19")
    monkeypatch.setattr(binaries, "ffmpeg_version", lambda _bin: "7.1.1")
    monkeypatch.setattr(binaries, "ytdlp_ejs_and_runtime", lambda _bin: ("0.8.0", "deno 2.9.7"))


@pytest.fixture
def client(settings: Settings, fake_binaries: None) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as client:
        yield client


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {"X-API-Key": "test-key"}


@pytest.fixture(autouse=True)
def public_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    # Unit tests never touch DNS: every name resolves to a public address unless a test overrides.
    from app.services import safe_url

    monkeypatch.setattr(safe_url, "resolve_host", lambda host: ["93.184.216.34"])
