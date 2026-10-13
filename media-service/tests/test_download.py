import json
import shutil
import subprocess
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.services import ytdlp
from tests.test_probe import YT_WITH_SUBS
from tests.test_subtitles import JSON3_MANUAL

FIXTURE_WAV = Path(__file__).parent / "fixtures" / "tone-10s.wav"
needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


@pytest.fixture
def url_source(client: TestClient, auth_headers, monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setattr(ytdlp, "dump_info", lambda _u, _s: YT_WITH_SUBS)
    resp = client.post("/probe", json={"url": "https://youtu.be/jNQXAC9IVRw"}, headers=auth_headers)
    return resp.json()["source_id"]


@pytest.fixture
def uploaded_source(client: TestClient, auth_headers) -> str:
    resp = client.post(
        "/upload",
        files={"file": ("tone.wav", FIXTURE_WAV.read_bytes(), "audio/wav")},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["source_id"]


def _download(client, headers, **body):
    return client.post("/download", json=body, headers=headers)


def test_unknown_source(client: TestClient, auth_headers) -> None:
    resp = _download(client, auth_headers, source_id="0123456789ab", mode="audio")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "source_not_found"


def test_subtitles_download_and_cache(
    client: TestClient, auth_headers, url_source: str, settings: Settings, monkeypatch
) -> None:
    calls: list[tuple[str, bool]] = []

    def fake_subs(url, lang, auto, out_dir: Path, _settings):
        calls.append((lang, auto))
        out_dir.mkdir(parents=True, exist_ok=True)
        target = out_dir / f"subs.{lang}.json3"
        target.write_text(JSON3_MANUAL, encoding="utf-8")
        return target

    monkeypatch.setattr(ytdlp, "download_subtitles", fake_subs)

    resp = _download(client, auth_headers, source_id=url_source, mode="subtitles_manual", lang="en")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["artifact"] == "subtitles"
    assert body["segments"] == 2
    path = Path(body["path"])
    assert path == settings.data_dir / url_source / "subs.en.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data[0] == {"start": 1.36, "end": 3.04, "text": "[♪♪♪]"}
    assert not (settings.data_dir / url_source / "raw").exists()

    # Second call is served from disk; yt-dlp is not invoked again.
    again = _download(
        client, auth_headers, source_id=url_source, mode="subtitles_manual", lang="en"
    )
    assert again.json() == body
    assert calls == [("en", False)]

    meta = json.loads((settings.data_dir / url_source / "meta.json").read_text())
    assert meta["operations"][-1]["op"] == "download"
    assert meta["operations"][-1]["result"]["raw_format"] == "json3"


def test_subtitles_auto_mode_flag(client, auth_headers, url_source, monkeypatch) -> None:
    seen = {}

    def fake_subs(url, lang, auto, out_dir: Path, _settings):
        seen["auto"] = auto
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "subs.ru-orig.json3").write_text(JSON3_MANUAL, encoding="utf-8")
        return out_dir / "subs.ru-orig.json3"

    monkeypatch.setattr(ytdlp, "download_subtitles", fake_subs)
    resp = _download(client, auth_headers, source_id=url_source, mode="subtitles_auto", lang="ru")
    assert resp.status_code == 200
    assert seen["auto"] is True
    assert resp.json()["path"].endswith("/subs.ru.json")


def test_subtitles_missing_lang(client, auth_headers, url_source, monkeypatch) -> None:
    monkeypatch.setattr(ytdlp, "download_subtitles", lambda *_a, **_k: None)
    resp = _download(client, auth_headers, source_id=url_source, mode="subtitles_manual", lang="fr")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "subtitles_not_found"


def test_subtitles_for_upload_rejected(client, auth_headers, uploaded_source) -> None:
    resp = _download(
        client, auth_headers, source_id=uploaded_source, mode="subtitles_manual", lang="en"
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "subtitles_not_found"


def test_download_requires_lang_for_subtitles(client, auth_headers, url_source) -> None:
    resp = _download(client, auth_headers, source_id=url_source, mode="subtitles_manual")
    assert resp.status_code == 422


def _ffprobe_json(path: Path) -> dict:
    out = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return json.loads(out)


@needs_ffmpeg
def test_upload_audio_makes_work_track_and_playback_then_removes_source(
    client, auth_headers, uploaded_source: str, settings: Settings
) -> None:
    src_dir = settings.data_dir / uploaded_source
    assert (src_dir / "source.wav").is_file()

    resp = _download(client, auth_headers, source_id=uploaded_source, mode="audio")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["artifact"] == "audio"
    assert body["path"] == str(src_dir / "audio.wav")
    assert body["playback_path"] == str(src_dir / "playback.mp3")
    assert body["duration_sec"] == pytest.approx(10.0, abs=0.1)
    assert body["size_mb"] == pytest.approx(0.3, abs=0.05)  # 10 s * 16 kHz * 16 bit mono

    assert not (src_dir / "source.wav").exists()
    work = _ffprobe_json(src_dir / "audio.wav")["streams"][0]
    assert (work["sample_rate"], work["channels"], work["codec_name"]) == ("16000", 1, "pcm_s16le")
    play = _ffprobe_json(src_dir / "playback.mp3")
    stream = play["streams"][0]
    assert (stream["sample_rate"], stream["channels"], stream["codec_name"]) == ("44100", 1, "mp3")
    assert float(play["format"]["duration"]) == pytest.approx(10.0, abs=0.2)
    assert not any(p.name.startswith(".") for p in src_dir.iterdir())

    # Idempotent: second call returns the same artifact without a source file.
    again = _download(client, auth_headers, source_id=uploaded_source, mode="audio")
    assert again.status_code == 200
    assert again.json()["path"] == body["path"]

    # Source gone and work track gone: nothing left to transcode from.
    (src_dir / "audio.wav").unlink()
    gone = _download(client, auth_headers, source_id=uploaded_source, mode="audio")
    assert gone.status_code == 410
    assert gone.json()["error"]["code"] == "source_not_found"


@needs_ffmpeg
def test_upload_stereo_source_keeps_stereo_playback(
    client, auth_headers, settings: Settings, tmp_path: Path
) -> None:
    stereo = tmp_path / "stereo.wav"
    subprocess.run(
        [
            "ffmpeg",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=2",
            "-ac",
            "2",
            "-ar",
            "44100",
            str(stereo),
        ],
        check=True,
    )
    sid = client.post(
        "/upload",
        files={"file": ("stereo.wav", stereo.read_bytes(), "audio/wav")},
        headers=auth_headers,
    ).json()["source_id"]
    resp = _download(client, auth_headers, source_id=sid, mode="audio")
    assert resp.status_code == 200, resp.text
    play = _ffprobe_json(settings.data_dir / sid / "playback.mp3")["streams"][0]
    assert play["channels"] == 2
    work = _ffprobe_json(settings.data_dir / sid / "audio.wav")["streams"][0]
    assert work["channels"] == 1


@needs_ffmpeg
def test_url_audio_download(client, auth_headers, url_source: str, settings: Settings, monkeypatch):
    def fake_audio(url, out_dir: Path, _settings):
        out_dir.mkdir(parents=True, exist_ok=True)
        target = out_dir / "audio.wav"
        shutil.copy(FIXTURE_WAV, target)
        return target

    monkeypatch.setattr(ytdlp, "download_audio", fake_audio)
    resp = _download(client, auth_headers, source_id=url_source, mode="audio")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    src_dir = settings.data_dir / url_source
    assert body["path"] == str(src_dir / "audio.wav")
    assert body["playback_path"] is None
    assert not (src_dir / "playback.mp3").exists()
    assert not (src_dir / "raw").exists()


@needs_ffmpeg
def test_mp3_work_format(tmp_path: Path, fake_binaries, auth_headers) -> None:
    from app.main import create_app

    settings = Settings(_env_file=None, data_dir=tmp_path, api_key="test-key", audio_format="mp3")
    with TestClient(create_app(settings)) as client:
        sid = client.post(
            "/upload",
            files={"file": ("t.wav", FIXTURE_WAV.read_bytes(), "audio/wav")},
            headers=auth_headers,
        ).json()["source_id"]
        body = _download(client, auth_headers, source_id=sid, mode="audio").json()
    assert body["path"].endswith("/audio.mp3")
    stream = _ffprobe_json(Path(body["path"]))["streams"][0]
    assert (stream["codec_name"], stream["sample_rate"], stream["channels"]) == ("mp3", "16000", 1)


def test_download_subtitles_args(settings: Settings, monkeypatch, tmp_path: Path) -> None:
    captured = {}

    def _run(args, **kwargs):
        captured["args"] = args
        (tmp_path / "subs.ru.vtt").write_text("WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nx\n")
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", _run)
    path = ytdlp.download_subtitles(
        "https://x/y", "ru", auto=False, out_dir=tmp_path, settings=settings
    )
    assert path == tmp_path / "subs.ru.vtt"
    args = captured["args"]
    assert "--write-subs" in args and "--skip-download" in args
    assert args[args.index("--sub-langs") + 1] == "ru,ru-.*"

    ytdlp.download_subtitles("https://x/y", "ru", auto=True, out_dir=tmp_path, settings=settings)
    assert "--write-auto-subs" in captured["args"]


def test_download_audio_args(settings: Settings, monkeypatch, tmp_path: Path) -> None:
    captured = {}

    def _run(args, **kwargs):
        captured["args"] = args
        (tmp_path / "audio.webm").write_bytes(b"x" * 10)
        (tmp_path / "audio.webm.part").write_bytes(b"x" * 100)
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", _run)
    path = ytdlp.download_audio("https://x/y", tmp_path, settings)
    assert path == tmp_path / "audio.webm"
    args = captured["args"]
    assert args[args.index("-f") + 1] == "bestaudio/best"
    assert "--no-playlist" in args


@needs_ffmpeg
def test_concurrent_audio_downloads_share_one_transcode(
    client, auth_headers, uploaded_source: str, settings: Settings, monkeypatch
) -> None:
    """Two jobs on one source_id at once (the same link from a post, the same file uploaded twice):
    both must get 200 and the same artifact, produced once. Before the lock both requests wrote the
    same temp file and the second rename failed with FileNotFoundError (500)."""
    import threading
    import time
    from concurrent.futures import ThreadPoolExecutor

    from app.services import ffmpeg

    calls: list[Path] = []
    lock = threading.Lock()

    def slow_transcode(src: Path, dst: Path, _settings) -> None:
        with lock:
            calls.append(dst)
        time.sleep(0.5)  # long enough for the second request to arrive while the first is busy
        shutil.copy(src, dst)

    monkeypatch.setattr(ffmpeg, "to_work_audio", slow_transcode)
    monkeypatch.setattr(
        ffmpeg, "to_playback", lambda src, dst, stereo, settings: shutil.copy(src, dst)
    )

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(_download, client, auth_headers, source_id=uploaded_source, mode="audio")
            for _ in range(2)
        ]
        responses = [f.result() for f in futures]

    assert [r.status_code for r in responses] == [200, 200], [r.text for r in responses]
    paths = {r.json()["path"] for r in responses}
    assert paths == {str(settings.data_dir / uploaded_source / "audio.wav")}
    assert len(calls) == 1, "the second request must reuse the artifact, not transcode again"
    src_dir = settings.data_dir / uploaded_source
    assert not any(p.name.startswith(".") for p in src_dir.iterdir())


@needs_ffmpeg
def test_busy_source_answers_409_after_the_wait_bound(
    auth_headers, tmp_path: Path, fake_binaries, monkeypatch
) -> None:
    """A producer stuck past SOURCE_LOCK_WAIT_SEC must not keep the second request hanging: it gets
    409 source_busy with a plain message instead of an orchestrator-side timeout."""
    import threading
    from concurrent.futures import ThreadPoolExecutor

    from app.main import create_app
    from app.services import ffmpeg

    settings = Settings(
        _env_file=None, data_dir=tmp_path, api_key="test-key", source_lock_wait_sec=1
    )
    release = threading.Event()

    def stuck_transcode(src: Path, dst: Path, _settings) -> None:
        release.wait(10)
        shutil.copy(src, dst)

    monkeypatch.setattr(ffmpeg, "to_work_audio", stuck_transcode)
    monkeypatch.setattr(
        ffmpeg, "to_playback", lambda src, dst, stereo, settings: shutil.copy(src, dst)
    )
    with TestClient(create_app(settings)) as client:
        sid = client.post(
            "/upload",
            files={"file": ("t.wav", FIXTURE_WAV.read_bytes(), "audio/wav")},
            headers=auth_headers,
        ).json()["source_id"]
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(_download, client, auth_headers, source_id=sid, mode="audio")
            time.sleep(0.2)  # the first request holds the lock inside the stuck transcode
            second = _download(client, auth_headers, source_id=sid, mode="audio")
            assert second.status_code == 409, second.text
            assert second.json()["error"]["code"] == "source_busy"
            assert "try again later" in second.json()["error"]["message"]
            release.set()
            assert first.result().status_code == 200
