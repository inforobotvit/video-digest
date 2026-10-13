import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.errors import ApiError
from app.services import probe, ytdlp

YT_WITH_SUBS: dict[str, Any] = {
    "_type": "video",
    "extractor": "youtube",
    "id": "jNQXAC9IVRw",
    "title": "Me at the zoo",
    "duration": 19,
    "language": None,
    "thumbnail": "https://i.ytimg.com/vi/jNQXAC9IVRw/hqdefault.jpg",
    "subtitles": {"en": [{"ext": "json3"}], "de": [{"ext": "vtt"}], "live_chat": [{"ext": "json"}]},
    "automatic_captions": {"en-orig": [{"ext": "json3"}], "ru": [{"ext": "json3"}]},
}

YT_AUTO_ONLY: dict[str, Any] = {
    "extractor": "youtube",
    "id": "abc123def45",
    "title": "No subs",
    "duration": 600.5,
    "language": "ru",
    "subtitles": {},
    "automatic_captions": {"ru-orig": [], "en": [], "de": []},
}

VK_PLAIN: dict[str, Any] = {
    "extractor": "vk",
    "id": "-123_456",
    "title": "VK clip",
    "duration": 42,
}


@pytest.fixture
def fake_ytdlp(monkeypatch: pytest.MonkeyPatch):
    def _install(info: dict[str, Any]) -> None:
        monkeypatch.setattr(ytdlp, "dump_info", lambda _url, _settings: info)

    return _install


def test_probe_manual_subs(client: TestClient, auth_headers, fake_ytdlp) -> None:
    fake_ytdlp(YT_WITH_SUBS)
    resp = client.post("/probe", json={"url": "https://youtu.be/jNQXAC9IVRw"}, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["platform"] == "youtube"
    assert body["title"] == "Me at the zoo"
    assert body["duration_sec"] == 19
    assert body["subtitles"] == {"manual": ["de", "en"], "auto": ["en"]}
    assert body["recommended"] == "subtitles_manual"
    assert body["language"] == "en"  # from the single "en-orig" auto track
    assert body["thumbnail_url"].startswith("https://i.ytimg.com/")
    assert len(body["source_id"]) == 12


def test_probe_auto_only_recommends_transcribe(client: TestClient, auth_headers, fake_ytdlp):
    fake_ytdlp(YT_AUTO_ONLY)
    resp = client.post("/probe", json={"url": "https://x.test/v"}, headers=auth_headers)
    body = resp.json()
    assert body["subtitles"] == {"manual": [], "auto": ["ru"]}
    assert body["recommended"] == "transcribe"
    assert body["language"] == "ru"


def test_probe_no_subs_at_all(client: TestClient, auth_headers, fake_ytdlp) -> None:
    fake_ytdlp(VK_PLAIN)
    body = client.post(
        "/probe", json={"url": "https://vk.com/video-123_456"}, headers=auth_headers
    ).json()
    assert body["platform"] == "vk"
    assert body["subtitles"] == {"manual": [], "auto": []}
    assert body["recommended"] == "transcribe"


def test_same_video_different_urls_same_id(client: TestClient, auth_headers, fake_ytdlp) -> None:
    fake_ytdlp(YT_WITH_SUBS)
    a = client.post("/probe", json={"url": "https://youtu.be/jNQXAC9IVRw"}, headers=auth_headers)
    b = client.post(
        "/probe", json={"url": "https://www.youtube.com/watch?v=jNQXAC9IVRw"}, headers=auth_headers
    )
    assert a.json()["source_id"] == b.json()["source_id"]


def test_probe_writes_meta_and_appends_history(
    client: TestClient, auth_headers, fake_ytdlp, settings: Settings
) -> None:
    fake_ytdlp(YT_WITH_SUBS)
    url = "https://youtu.be/jNQXAC9IVRw"
    sid = client.post("/probe", json={"url": url}, headers=auth_headers).json()["source_id"]
    client.post("/probe", json={"url": url}, headers=auth_headers)

    meta = json.loads((settings.data_dir / sid / "meta.json").read_text())
    assert meta["kind"] == "url"
    assert meta["url"] == url
    assert meta["probe"]["source_id"] == sid
    assert [op["op"] for op in meta["operations"]] == ["probe", "probe"]


def test_playlist_is_unsupported(client: TestClient, auth_headers, fake_ytdlp) -> None:
    fake_ytdlp({"_type": "playlist", "extractor": "youtube:tab", "id": "PL1", "entries": []})
    resp = client.post(
        "/probe", json={"url": "https://youtube.com/playlist?list=PL1"}, headers=auth_headers
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "unsupported_url"


def test_invalid_url_is_validation_error(client: TestClient, auth_headers) -> None:
    resp = client.post("/probe", json={"url": "not a url"}, headers=auth_headers)
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "validation_error"


@pytest.mark.parametrize(
    ("stderr", "code", "status"),
    [
        ("ERROR: [youtube] yZIXLfi8CZQ: Private video", "private_or_removed", 404),
        ("ERROR: [youtube] aaaaaaaaaaa: This video is unavailable", "private_or_removed", 404),
        ("ERROR: [vk] Access restricted", "private_or_removed", 404),
        (
            "ERROR: [youtube] x: Sign in to confirm you're not a bot. Use --cookies-from-browser",
            "bot_check",
            403,
        ),
        ("ERROR: Unsupported URL: https://example.com/page", "unsupported_url", 400),
        (
            "ERROR: [generic] nothing-here: Unable to download webpage: HTTP Error 404: Not Found",
            "unsupported_url",
            400,
        ),
        ("ERROR: something entirely new", "ytdlp_failed", 502),
    ],
)
def test_map_error(stderr: str, code: str, status: int) -> None:
    err = ytdlp.map_error(stderr)
    assert (err.code, err.status_code) == (code, status)


def test_probe_error_propagates_to_http(
    client: TestClient, auth_headers, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _fail(_url, _settings):
        raise ytdlp.map_error("ERROR: [youtube] yZIXLfi8CZQ: Private video")

    monkeypatch.setattr(ytdlp, "dump_info", _fail)
    resp = client.post("/probe", json={"url": "https://youtu.be/yZIXLfi8CZQ"}, headers=auth_headers)
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "private_or_removed"


def test_run_maps_timeout(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    def _timeout(*_a, **_k):
        raise subprocess.TimeoutExpired(cmd="yt-dlp", timeout=1)

    monkeypatch.setattr(subprocess, "run", _timeout)
    with pytest.raises(ApiError) as exc:
        ytdlp.run(["yt-dlp", "--version"], timeout_sec=1)
    assert exc.value.code == "ytdlp_timeout"
    assert exc.value.status_code == 504


def test_dump_info_args(settings: Settings, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    captured: dict[str, Any] = {}

    def _run(args, **kwargs):
        captured["args"] = args
        return subprocess.CompletedProcess(args, 0, stdout=json.dumps(VK_PLAIN), stderr="")

    monkeypatch.setattr(subprocess, "run", _run)
    cookies = tmp_path / "cookies.txt"
    cookies.touch()
    s = settings.model_copy(update={"ytdlp_cookies_file": cookies, "ytdlp_proxy": "socks5://p:1"})
    assert ytdlp.dump_info("https://vk.com/video-1_2", s) == VK_PLAIN
    args = captured["args"]
    assert args[0] == "yt-dlp"
    for flag in ("--dump-single-json", "--skip-download", "--no-playlist", "--flat-playlist"):
        assert flag in args
    assert args[args.index("--cookies") + 1] == str(cookies)
    assert args[args.index("--proxy") + 1] == "socks5://p:1"
    assert args[-2:] == ["--", "https://vk.com/video-1_2"]


def test_guess_language_prefers_manual_subtitles() -> None:
    """Rule 1.1: a manual track defines the language even when the metadata says otherwise."""
    ted_ed = {"language": "en", "subtitles": {"ru": []}, "automatic_captions": {"en": []}}
    assert probe.guess_language(ted_ed, probe.subtitle_languages(ted_ed)) == "ru"
    # several manual tracks: metadata language when it is one of them
    multi = {"language": "en", "subtitles": {"de": [], "en": []}, "automatic_captions": {}}
    assert probe.guess_language(multi, probe.subtitle_languages(multi)) == "en"
    # metadata outside the manual tracks: the spoken-language auto track if it is manual too
    orig = {"language": "fr", "subtitles": {"de": [], "en": []}}
    orig["automatic_captions"] = {"en-orig": []}
    assert probe.guess_language(orig, probe.subtitle_languages(orig)) == "en"
    # nothing matches: the first manual track
    first = {"language": None, "subtitles": {"de": [], "ru": []}}
    first["automatic_captions"] = {"en-orig": []}
    assert probe.guess_language(first, probe.subtitle_languages(first)) == "de"
    # no manual tracks: metadata, then the single auto track
    assert probe.guess_language({"language": "es"}, probe.subtitle_languages({})) == "es"
    auto = {"automatic_captions": {"ru-orig": []}}
    assert probe.guess_language(auto, probe.subtitle_languages(auto)) == "ru"
    assert probe.guess_language({}, probe.subtitle_languages({})) is None


def test_subtitle_languages_fallback_without_orig() -> None:
    subs = probe.subtitle_languages({"automatic_captions": {"en": [], "de": []}})
    assert subs.auto == ["de", "en"]
    subs = probe.subtitle_languages({"language": "en", "automatic_captions": {"en": [], "de": []}})
    assert subs.auto == ["en"]
