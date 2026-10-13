"""Real yt-dlp / ffmpeg end-to-end. Skipped by default (pyproject addopts), run with:

uv run pytest -m network
"""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings

FIXTURE_WAV = Path(__file__).parent / "fixtures" / "tone-10s.wav"
ME_AT_THE_ZOO = "https://www.youtube.com/watch?v=jNQXAC9IVRw"

pytestmark = pytest.mark.network


def test_youtube_probe_and_manual_subtitles(client: TestClient, auth_headers, settings: Settings):
    probe = client.post("/probe", json={"url": ME_AT_THE_ZOO}, headers=auth_headers)
    assert probe.status_code == 200, probe.text
    body = probe.json()
    assert body["platform"] == "youtube"
    assert body["title"] == "Me at the zoo"
    assert body["duration_sec"] == pytest.approx(19, abs=1)
    assert "en" in body["subtitles"]["manual"]
    assert body["recommended"] == "subtitles_manual"
    sid = body["source_id"]

    # Same video via the short URL form -> same source_id.
    short = client.post(
        "/probe", json={"url": "https://youtu.be/jNQXAC9IVRw"}, headers=auth_headers
    )
    assert short.json()["source_id"] == sid

    subs = client.post(
        "/download",
        json={"source_id": sid, "mode": "subtitles_manual", "lang": "en"},
        headers=auth_headers,
    )
    assert subs.status_code == 200, subs.text
    assert subs.json()["artifact"] == "subtitles"
    assert subs.json()["segments"] > 0

    segments = json.loads((settings.data_dir / sid / "subs.en.json").read_text(encoding="utf-8"))
    assert all(0 <= s["start"] <= s["end"] <= 25 and s["text"] for s in segments)
    assert not (settings.data_dir / sid / "raw").exists()

    served = client.get(f"/artifacts/{sid}/subs.en.json")
    assert served.status_code == 200
    assert served.json() == segments

    gone = client.delete(f"/sources/{sid}", headers=auth_headers).json()
    assert gone["deleted"] is True
    assert not (settings.data_dir / sid).exists()


def test_youtube_private_video_error(client: TestClient, auth_headers) -> None:
    resp = client.post(
        "/probe", json={"url": "https://www.youtube.com/watch?v=yZIXLfi8CZQ"}, headers=auth_headers
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "private_or_removed"


def test_local_wav_full_path(client: TestClient, auth_headers, settings: Settings) -> None:
    up = client.post(
        "/upload",
        files={"file": ("tone-10s.wav", FIXTURE_WAV.read_bytes(), "audio/wav")},
        headers=auth_headers,
    )
    assert up.status_code == 200, up.text
    assert up.json()["platform"] == "upload"
    assert up.json()["recommended"] == "transcribe"
    sid = up.json()["source_id"]
    src_dir = settings.data_dir / sid

    audio = client.post("/download", json={"source_id": sid, "mode": "audio"}, headers=auth_headers)
    assert audio.status_code == 200, audio.text
    assert audio.json()["duration_sec"] == pytest.approx(10.0, abs=0.1)
    assert audio.json()["playback_path"] == str(src_dir / "playback.mp3")
    assert not (src_dir / "source.wav").exists()

    split = client.post("/split", json={"source_id": sid, "chunk_sec": 4}, headers=auth_headers)
    assert split.status_code == 200, split.text
    chunks = split.json()["chunks"]
    assert [(c["start"], c["end"]) for c in chunks] == [(0.0, 4.0), (4.0, 8.0), (8.0, 10.0)]
    for c in chunks:
        assert client.get(f"/artifacts/{sid}/chunks/{c['index']:03d}.mp3").status_code == 200

    part = client.get(f"/artifacts/{sid}/playback.mp3", headers={"Range": "bytes=0-99"})
    assert part.status_code == 206
    assert part.headers["content-range"].startswith("bytes 0-99/")

    kept = client.delete(f"/sources/{sid}?keep=playback", headers=auth_headers).json()
    assert kept["kept"] == ["playback.mp3"]
    assert {p.name for p in src_dir.iterdir()} == {"meta.json", "playback.mp3"}
