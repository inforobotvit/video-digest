from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.services import binaries


def test_health_ok(client: TestClient) -> None:
    resp = client.get("/health")

    assert resp.status_code == 200
    assert resp.json() == {
        "status": "ok",
        "ytdlp": "2026.08.19",
        "ffmpeg": "7.1.1",
        "ejs": "0.8.0",
        "js_runtime": "deno 2.9.7",
    }


def test_health_degraded_when_binary_missing(
    tmp_path: Path, fake_binaries: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(binaries, "ytdlp_version", lambda _bin: None)
    settings = Settings(_env_file=None, data_dir=tmp_path)
    with TestClient(create_app(settings)) as client:
        resp = client.get("/health")

    assert resp.status_code == 200
    assert resp.json() == {
        "status": "degraded",
        "ytdlp": None,
        "ffmpeg": "7.1.1",
        "ejs": "0.8.0",
        "js_runtime": "deno 2.9.7",
    }


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "[debug] Optional libraries: yt_dlp_ejs-0.8.0\n[debug] JS runtimes: none\n",
            ("0.8.0", None),
        ),
        (
            "[debug] Optional libraries: yt_dlp_ejs-0.8.0\n[debug] JS runtimes: deno 2.9.7\n",
            ("0.8.0", "deno 2.9.7"),
        ),
        ("nothing here", (None, None)),
    ],
)
def test_parse_ytdlp_debug(text: str, expected: tuple[str | None, str | None]) -> None:
    assert binaries.parse_ytdlp_debug(text) == expected


def test_health_does_not_require_api_key(client: TestClient) -> None:
    assert client.get("/health").status_code == 200


def test_startup_creates_data_dir(settings: Settings, client: TestClient) -> None:
    assert settings.data_dir.is_dir()


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("ffmpeg version 7.1.1 Copyright (c) 2000-2025 the FFmpeg developers", "7.1.1"),
        ("ffmpeg version n7.1-static https://johnvansickle.com/ffmpeg/", "n7.1-static"),
        ("garbage", None),
    ],
)
def test_parse_ffmpeg_version(line: str, expected: str | None) -> None:
    assert binaries.parse_ffmpeg_version(line) == expected


def test_missing_binary_returns_none() -> None:
    assert binaries.ytdlp_version("/definitely/not/a/binary") is None
