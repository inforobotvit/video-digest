import json
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.services import split
from app.services.split import Silence, parse_silencedetect, plan_boundaries

FIXTURE_WAV = Path(__file__).parent / "fixtures" / "tone-10s.wav"
needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")

SILENCEDETECT_STDERR = """
[silencedetect @ 0x1] silence_start: 6.159375
[silencedetect @ 0x1] silence_end: 6.577313 | silence_duration: 0.417938
size=N/A time=00:00:10.00 bitrate=N/A speed= 500x
[silencedetect @ 0x1] silence_start: 8.406937
[silencedetect @ 0x1] silence_end: 9.035625 | silence_duration: 0.628688
[silencedetect @ 0x1] silence_start: 312.8415
"""


def test_parse_silencedetect_pairs_and_closes_trailing() -> None:
    sil = parse_silencedetect(SILENCEDETECT_STDERR, duration=313.78)
    assert sil == [
        Silence(6.159375, 6.577313),
        Silence(8.406937, 9.035625),
        Silence(312.8415, 313.78),
    ]


def test_plan_snaps_to_closest_silence_in_window() -> None:
    silences = [Silence(105.0, 106.0), Silence(112.0, 113.0), Silence(250.0, 251.0)]
    cuts = plan_boundaries(300.0, 120.0, silences, window_sec=20)
    # First target 120: silences at 105.5 (d=14.5) and 112.5 (d=7.5) -> 112.5.
    # Second target 232.5: silence at 250.5 (d=18) is inside the window -> 250.5.
    assert cuts == [112.5, 250.5]


def test_plan_exact_when_no_silence_in_window() -> None:
    silences = [Silence(50.0, 51.0)]  # 70 s away from the first target
    assert plan_boundaries(300.0, 120.0, silences, window_sec=20) == [120.0, 240.0]


def test_plan_clamps_silence_midpoint_into_window() -> None:
    # Long silence 95..145 has midpoint 120 (fine); silence 130..170 has midpoint 150 -> clamp 140.
    assert plan_boundaries(300.0, 120.0, [Silence(130.0, 170.0)], window_sec=20) == [140.0, 260.0]


def test_plan_short_audio_and_tail_merge() -> None:
    assert plan_boundaries(100.0, 120.0, [], window_sec=20) == []
    # 10 s with 3 s chunks: cuts at 3 and 6; remainder 4 s > 3+1 is false -> last chunk 6..10.
    assert plan_boundaries(10.0, 3.0, [], window_sec=20) == [3.0, 6.0]


def test_max_chunk_sec_for_size() -> None:
    # 24 MB at 64 kbps: 24*1024*1024*8/64000 = 3145.7 s, minus 5% headroom.
    assert split.max_chunk_sec_for_size(24, "64k") == pytest.approx(2988.4, abs=0.1)
    assert split.max_chunk_sec_for_size(1, "128k") < split.max_chunk_sec_for_size(1, "64k")


def test_split_unknown_source(client: TestClient, auth_headers) -> None:
    resp = client.post("/split", json={"source_id": "0123456789ab"}, headers=auth_headers)
    assert resp.status_code == 404


def test_split_without_audio_is_409(client: TestClient, auth_headers) -> None:
    sid = client.post(
        "/upload",
        files={"file": ("t.wav", FIXTURE_WAV.read_bytes(), "audio/wav")},
        headers=auth_headers,
    ).json()["source_id"]
    resp = client.post("/split", json={"source_id": sid}, headers=auth_headers)
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "audio_not_found"


def _ffprobe_duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return float(out)


def _make_speechlike(path: Path) -> None:
    """30 s tone with silences at 9.0-9.6 s and 20.5-21.0 s."""
    gate = "volume=0:enable='between(t,9,9.6)+between(t,20.5,21)'"
    subprocess.run(
        [
            "ffmpeg",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=300:duration=30",
            "-af",
            gate,
            "-ac",
            "1",
            "-ar",
            "16000",
            str(path),
        ],
        check=True,
    )


def _prepare_audio(client: TestClient, headers, wav: Path) -> str:
    sid = client.post(
        "/upload", files={"file": (wav.name, wav.read_bytes(), "audio/wav")}, headers=headers
    ).json()["source_id"]
    assert (
        client.post(
            "/download", json={"source_id": sid, "mode": "audio"}, headers=headers
        ).status_code
        == 200
    )
    return sid


@needs_ffmpeg
def test_split_snaps_to_silence_and_covers_whole_file(
    client: TestClient, auth_headers, settings: Settings, tmp_path: Path
) -> None:
    wav = tmp_path / "speechlike.wav"
    _make_speechlike(wav)
    sid = _prepare_audio(client, auth_headers, wav)

    resp = client.post("/split", json={"source_id": sid, "chunk_sec": 10}, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    chunks = resp.json()["chunks"]
    assert [c["index"] for c in chunks] == [0, 1, 2]
    assert chunks[0]["start"] == 0.0
    assert chunks[0]["end"] == pytest.approx(9.3, abs=0.15)  # middle of the 9.0-9.6 silence
    assert chunks[1]["end"] == pytest.approx(20.75, abs=0.15)  # middle of the 20.5-21.0 silence
    assert chunks[2]["end"] == pytest.approx(30.0, abs=0.01)
    # Contiguous: no gaps, no overlap.
    for a, b in zip(chunks, chunks[1:], strict=False):
        assert a["end"] == b["start"]
    assert sum(c["end"] - c["start"] for c in chunks) == pytest.approx(30.0, abs=0.01)

    for c in chunks:
        p = Path(c["path"])
        assert p.is_file() and p.parent == settings.data_dir / sid / "chunks"
        assert _ffprobe_duration(p) == pytest.approx(c["end"] - c["start"], abs=0.1)
        assert p.stat().st_size <= 24 * 1024 * 1024

    manifest = json.loads((settings.data_dir / sid / "chunks" / "manifest.json").read_text())
    assert manifest["params"]["chunk_sec"] == 10.0

    # Same params: served from the manifest, files untouched.
    before = {c["path"]: Path(c["path"]).stat().st_mtime_ns for c in chunks}
    again = client.post("/split", json={"source_id": sid, "chunk_sec": 10}, headers=auth_headers)
    assert again.json() == resp.json()
    assert {c["path"]: Path(c["path"]).stat().st_mtime_ns for c in chunks} == before

    # Different params: re-cut. chunk_sec=25 -> single cut at the 20.75 silence.
    recut = client.post("/split", json={"source_id": sid, "chunk_sec": 25}, headers=auth_headers)
    recut_chunks = recut.json()["chunks"]
    assert [c["index"] for c in recut_chunks] == [0, 1]
    assert recut_chunks[0]["end"] == pytest.approx(20.75, abs=0.15)
    assert not (settings.data_dir / sid / "chunks" / "002.mp3").exists()


@needs_ffmpeg
def test_split_exact_cuts_without_silence(
    client: TestClient, auth_headers, settings: Settings
) -> None:
    sid = _prepare_audio(client, auth_headers, FIXTURE_WAV)  # continuous tone, no silence
    resp = client.post("/split", json={"source_id": sid, "chunk_sec": 3}, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    chunks = resp.json()["chunks"]
    assert [(c["start"], c["end"]) for c in chunks] == [(0.0, 3.0), (3.0, 6.0), (6.0, 10.0)]


@needs_ffmpeg
def test_split_max_mb_caps_chunk_length(client: TestClient, auth_headers) -> None:
    sid = _prepare_audio(client, auth_headers, FIXTURE_WAV)
    # 0.03 MB at 64 kbps ~ 3.7 s -> chunk_sec=600 must be capped well below 10 s.
    resp = client.post(
        "/split", json={"source_id": sid, "chunk_sec": 600, "max_mb": 0.03}, headers=auth_headers
    )
    assert resp.status_code == 200, resp.text
    chunks = resp.json()["chunks"]
    assert len(chunks) >= 2
    for c in chunks:
        assert Path(c["path"]).stat().st_size <= 0.03 * 1024 * 1024
