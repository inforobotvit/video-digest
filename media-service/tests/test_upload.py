import asyncio
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.errors import ApiError
from app.main import create_app
from app.services import ffprobe, upload

FIXTURE_WAV = Path(__file__).parent / "fixtures" / "tone-10s.wav"


@pytest.fixture
def fake_ffprobe(monkeypatch: pytest.MonkeyPatch):
    def _install(
        has_audio: bool = True, has_video: bool = False, duration: float | None = 10.0
    ) -> None:
        monkeypatch.setattr(
            ffprobe,
            "probe_file",
            lambda _p, _s: ffprobe.MediaInfo(
                duration_sec=duration, format_name="wav", has_audio=has_audio, has_video=has_video
            ),
        )

    return _install


def _upload(client: TestClient, headers, name: str, payload: bytes):
    return client.post(
        "/upload", files={"file": (name, payload, "application/octet-stream")}, headers=headers
    )


def test_upload_ok(client: TestClient, auth_headers, fake_ffprobe, settings: Settings) -> None:
    fake_ffprobe()
    resp = _upload(client, auth_headers, "Лекция 1.mp4", b"\x00" * 2048)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["platform"] == "upload"
    assert body["title"] == "Лекция 1"
    assert body["duration_sec"] == 10.0
    assert body["subtitles"] == {"manual": [], "auto": []}
    assert body["recommended"] == "transcribe"

    src_dir = settings.data_dir / body["source_id"]
    assert (src_dir / "source.mp4").stat().st_size == 2048
    assert (src_dir / "meta.json").is_file()
    assert not list((settings.data_dir / ".tmp").iterdir())


def test_upload_same_content_same_id(client: TestClient, auth_headers, fake_ffprobe) -> None:
    fake_ffprobe()
    a = _upload(client, auth_headers, "a.mp3", b"same-bytes" * 100).json()
    b = _upload(client, auth_headers, "b.mp3", b"same-bytes" * 100).json()
    assert a["source_id"] == b["source_id"]
    assert b["title"] == "a"  # first upload wins; second is deduplicated


def test_upload_rejects_extension(client: TestClient, auth_headers) -> None:
    resp = _upload(client, auth_headers, "notes.txt", b"hello")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "unsupported_file"


def test_upload_rejects_no_audio(client: TestClient, auth_headers, fake_ffprobe, settings) -> None:
    fake_ffprobe(has_audio=False, has_video=True)
    resp = _upload(client, auth_headers, "silent.mp4", b"\x00" * 100)
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "no_audio"
    assert [p.name for p in settings.data_dir.iterdir()] == [".tmp"]


def test_upload_rejects_non_media(client: TestClient, auth_headers, fake_ffprobe) -> None:
    fake_ffprobe(has_audio=False, has_video=False)
    resp = _upload(client, auth_headers, "fake.mp4", b"not media")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "invalid_media"


def test_upload_too_large_declared(tmp_path: Path, fake_binaries, fake_ffprobe) -> None:
    fake_ffprobe()
    settings = Settings(_env_file=None, data_dir=tmp_path, api_key="", upload_max_mb=1)
    with TestClient(create_app(settings)) as client:
        resp = _upload(client, {}, "big.wav", b"\x01" * (1024 * 1024 + 1))
    assert resp.status_code == 413
    assert resp.json()["error"]["code"] == "file_too_large"


def test_save_upload_streaming_limit(tmp_path: Path, fake_ffprobe) -> None:
    # Content-Length can lie (or be absent with chunked encoding): the byte counter must catch it.
    fake_ffprobe()
    settings = Settings(_env_file=None, data_dir=tmp_path, upload_max_mb=1)

    async def chunks():
        for _ in range(3):
            yield b"\x01" * (512 * 1024)

    with pytest.raises(ApiError) as exc:
        asyncio.run(upload.save_upload(chunks(), "big.wav", settings))
    assert exc.value.code == "file_too_large"
    assert not list((tmp_path / ".tmp").iterdir())


def test_upload_requires_api_key(client: TestClient) -> None:
    assert _upload(client, {}, "a.wav", b"x").status_code == 401


@pytest.mark.skipif(shutil.which("ffprobe") is None, reason="ffprobe not installed")
def test_upload_real_wav_fixture(client: TestClient, auth_headers) -> None:
    resp = _upload(client, auth_headers, FIXTURE_WAV.name, FIXTURE_WAV.read_bytes())
    assert resp.status_code == 200, resp.text
    assert resp.json()["duration_sec"] == pytest.approx(10.0, abs=0.05)
