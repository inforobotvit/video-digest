import json
import os
import shutil
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.services import retention, ytdlp
from tests.test_probe import YT_WITH_SUBS
from tests.test_subtitles import JSON3_MANUAL

FIXTURE_WAV = Path(__file__).parent / "fixtures" / "tone-10s.wav"
needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
HOUR = 3600
DAY = 86400


@pytest.fixture
def uploaded(client: TestClient, auth_headers) -> str:
    return client.post(
        "/upload",
        files={"file": ("t.wav", FIXTURE_WAV.read_bytes(), "audio/wav")},
        headers=auth_headers,
    ).json()["source_id"]


@pytest.fixture
def with_audio(client: TestClient, auth_headers, uploaded: str) -> str:
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg not installed")
    assert (
        client.post(
            "/download", json={"source_id": uploaded, "mode": "audio"}, headers=auth_headers
        ).status_code
        == 200
    )
    return uploaded


# --- GET /artifacts ---------------------------------------------------------


@needs_ffmpeg
def test_artifact_full_and_range(client: TestClient, with_audio: str, settings: Settings) -> None:
    size = (settings.data_dir / with_audio / "playback.mp3").stat().st_size

    full = client.get(f"/artifacts/{with_audio}/playback.mp3")  # no API key needed for GET
    assert full.status_code == 200
    assert full.headers["accept-ranges"] == "bytes"
    assert full.headers["content-type"] == "audio/mpeg"
    assert len(full.content) == size

    part = client.get(f"/artifacts/{with_audio}/playback.mp3", headers={"Range": "bytes=100-199"})
    assert part.status_code == 206
    assert part.headers["content-range"] == f"bytes 100-199/{size}"
    assert part.headers["content-length"] == "100"
    assert part.content == full.content[100:200]

    tail = client.get(
        f"/artifacts/{with_audio}/playback.mp3", headers={"Range": f"bytes={size - 10}-"}
    )
    assert tail.status_code == 206
    assert tail.content == full.content[-10:]

    bad = client.get(
        f"/artifacts/{with_audio}/playback.mp3", headers={"Range": f"bytes={size + 5}-"}
    )
    assert bad.status_code == 416
    assert bad.headers["content-range"] == f"bytes */{size}"


@needs_ffmpeg
def test_artifact_chunks_and_wav(client: TestClient, auth_headers, with_audio: str) -> None:
    client.post("/split", json={"source_id": with_audio, "chunk_sec": 4}, headers=auth_headers)
    assert client.get(f"/artifacts/{with_audio}/chunks/000.mp3").status_code == 200
    wav = client.get(f"/artifacts/{with_audio}/audio.wav")
    assert wav.status_code == 200
    assert wav.headers["content-type"] == "audio/wav"


def test_artifact_subtitles_json(client: TestClient, auth_headers, monkeypatch, settings) -> None:
    monkeypatch.setattr(ytdlp, "dump_info", lambda _u, _s: YT_WITH_SUBS)
    sid = client.post("/probe", json={"url": "https://youtu.be/x"}, headers=auth_headers).json()[
        "source_id"
    ]

    def fake_subs(url, lang, auto, out_dir: Path, _s):
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "subs.en.json3").write_text(JSON3_MANUAL)
        return out_dir / "subs.en.json3"

    monkeypatch.setattr(ytdlp, "download_subtitles", fake_subs)
    client.post(
        "/download",
        json={"source_id": sid, "mode": "subtitles_manual", "lang": "en"},
        headers=auth_headers,
    )
    resp = client.get(f"/artifacts/{sid}/subs.en.json")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/json"
    assert len(resp.json()) == 2


@pytest.mark.parametrize(
    "name",
    [
        "meta.json",
        "source.wav",
        "chunks/manifest.json",
        "raw/audio/audio.webm",
        "nope.mp3",
    ],
)
def test_artifact_denylist(client: TestClient, uploaded: str, name: str) -> None:
    resp = client.get(f"/artifacts/{uploaded}/{name}")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"


def test_artifact_resolve_blocks_traversal(settings: Settings, uploaded: str) -> None:
    from app.errors import ApiError
    from app.services import artifacts

    with pytest.raises(ApiError):
        artifacts.resolve(settings, uploaded, "../" + uploaded + "/source.wav")
    with pytest.raises(ApiError):
        artifacts.resolve(settings, uploaded, "chunks/../source.wav")


def test_artifact_missing_file(client: TestClient, uploaded: str) -> None:
    assert client.get(f"/artifacts/{uploaded}/audio.wav").status_code == 404


# --- DELETE /sources --------------------------------------------------------


def test_delete_requires_key_and_is_idempotent(
    client: TestClient, auth_headers, uploaded, settings
) -> None:
    assert client.delete(f"/sources/{uploaded}").status_code == 401
    resp = client.delete(f"/sources/{uploaded}", headers=auth_headers)
    assert resp.json() == {"deleted": True, "source_id": uploaded, "kept": []}
    assert not (settings.data_dir / uploaded).exists()
    again = client.delete(f"/sources/{uploaded}", headers=auth_headers)
    assert again.status_code == 200
    assert again.json()["deleted"] is False


@needs_ffmpeg
def test_delete_keep_playback(
    client: TestClient, auth_headers, with_audio: str, settings: Settings
) -> None:
    client.post("/split", json={"source_id": with_audio, "chunk_sec": 4}, headers=auth_headers)
    src_dir = settings.data_dir / with_audio
    assert {p.name for p in src_dir.iterdir()} == {
        "meta.json",
        "audio.wav",
        "playback.mp3",
        "chunks",
    }

    resp = client.delete(f"/sources/{with_audio}?keep=playback", headers=auth_headers)
    assert resp.json() == {"deleted": True, "source_id": with_audio, "kept": ["playback.mp3"]}
    assert {p.name for p in src_dir.iterdir()} == {"meta.json", "playback.mp3"}
    meta = json.loads((src_dir / "meta.json").read_text())
    assert meta["operations"][-1]["op"] == "delete"
    # playback still served after the cleanup
    assert client.get(f"/artifacts/{with_audio}/playback.mp3").status_code == 200


def test_delete_keep_playback_without_playback_removes_all(
    client, auth_headers, uploaded, settings
) -> None:
    resp = client.delete(f"/sources/{uploaded}?keep=playback", headers=auth_headers)
    assert resp.json()["kept"] == []
    assert not (settings.data_dir / uploaded).exists()


def test_delete_bad_keep_value(client: TestClient, auth_headers, uploaded: str) -> None:
    assert (
        client.delete(f"/sources/{uploaded}?keep=everything", headers=auth_headers).status_code
        == 422
    )


# --- retention sweep --------------------------------------------------------


def _fake_source(data_dir: Path, sid: str, age_sec: float, playback_age_sec: float | None) -> Path:
    """A source dir with working artifacts aged age_sec and an optional playback.mp3."""
    src = data_dir / sid
    (src / "chunks").mkdir(parents=True)
    for rel in ("meta.json", "audio.wav", "subs.en.json", "chunks/000.mp3", "chunks/manifest.json"):
        (src / rel).write_bytes(b"x")
    if playback_age_sec is not None:
        (src / "playback.mp3").write_bytes(b"p")
    old = time.time() - age_sec
    for path in [src, *src.rglob("*")]:
        if path.name != "playback.mp3":
            os.utime(path, (old, old))
    if playback_age_sec is not None:
        p_old = time.time() - playback_age_sec
        os.utime(src / "playback.mp3", (p_old, p_old))
    return src


def test_sweep_removes_work_keeps_fresh_playback(settings: Settings) -> None:
    settings.data_dir.mkdir()
    old_work = _fake_source(
        settings.data_dir, "aaaaaaaaaaa1", age_sec=49 * HOUR, playback_age_sec=49 * HOUR
    )
    all_old = _fake_source(
        settings.data_dir, "aaaaaaaaaaa2", age_sec=40 * DAY, playback_age_sec=31 * DAY
    )
    fresh = _fake_source(
        settings.data_dir, "aaaaaaaaaaa3", age_sec=1 * HOUR, playback_age_sec=1 * HOUR
    )
    url_old = _fake_source(
        settings.data_dir, "aaaaaaaaaaa4", age_sec=49 * HOUR, playback_age_sec=None
    )
    tmp = settings.data_dir / ".tmp"
    tmp.mkdir()
    (tmp / "upload-1.mp4").write_bytes(b"t")
    os.utime(tmp / "upload-1.mp4", (time.time() - 3 * DAY,) * 2)

    report = retention.sweep(settings)

    assert report.checked == 4
    assert {p.name for p in old_work.iterdir()} == {"meta.json", "playback.mp3"}
    assert not all_old.exists()
    assert {p.name for p in fresh.iterdir()} == {
        "meta.json",
        "audio.wav",
        "subs.en.json",
        "chunks",
        "playback.mp3",
    }
    assert not url_old.exists()
    assert not (tmp / "upload-1.mp4").exists()
    assert report.sources_removed == ["aaaaaaaaaaa2", "aaaaaaaaaaa4"]
    assert str(old_work / "audio.wav") in report.removed
    assert str(fresh / "audio.wav") not in report.removed


def test_sweep_is_stable_on_second_run(settings: Settings) -> None:
    settings.data_dir.mkdir()
    _fake_source(settings.data_dir, "aaaaaaaaaaa1", age_sec=49 * HOUR, playback_age_sec=1 * HOUR)
    retention.sweep(settings)
    second = retention.sweep(settings)
    assert second.removed == [] and second.sources_removed == []


def test_sweep_endpoint(client: TestClient, auth_headers, settings: Settings) -> None:
    _fake_source(settings.data_dir, "aaaaaaaaaaa9", age_sec=49 * HOUR, playback_age_sec=None)
    assert client.post("/maintenance/sweep").status_code == 401
    resp = client.post("/maintenance/sweep", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["checked"] == 1
    assert body["sources_removed"] == ["aaaaaaaaaaa9"]
