"""SSRF guard for user-supplied links (decision of 2026-09-17): only public http(s) addresses,
checked on every redirect; the tests for localhost, 127.0.0.1, 169.254.169.254 and the private
ranges are a release condition."""

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.errors import ApiError
from app.services import ffprobe, probe, safe_url, ytdlp
from app.services.ffprobe import MediaInfo


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost/a.mp3",
        "http://LOCALHOST:8000/a.mp3",
        "http://media.localhost/a.mp3",
        "http://printer.local/a.mp3",
        "http://db.internal/a.mp3",
        "http://127.0.0.1/a.mp3",
        "http://127.8.8.8/a.mp3",
        "http://0.0.0.0/a.mp3",
        "http://169.254.169.254/latest/meta-data/",
        "http://169.254.1.1/a.mp3",
        "http://10.0.0.5/a.mp3",
        "http://172.16.0.9/a.mp3",
        "http://172.31.255.1/a.mp3",
        "http://192.168.1.1/a.mp3",
        "http://100.64.0.1/a.mp3",
        "http://224.0.0.1/a.mp3",
        "http://[::1]/a.mp3",
        "http://[fd00::1]/a.mp3",
        "http://[fe80::1]/a.mp3",
        "http://[::ffff:127.0.0.1]/a.mp3",
        "http://[::ffff:169.254.169.254]/a.mp3",
        "ftp://example.com/a.mp3",
        "file:///etc/passwd",
        "gopher://example.com/",
        "http:///a.mp3",
    ],
)
def test_rejects_non_public_or_non_http(url: str) -> None:
    with pytest.raises(ApiError) as exc:
        safe_url.check_public_url(url)
    assert exc.value.code == "unsupported_url"


@pytest.mark.parametrize(
    "resolved",
    [["127.0.0.1"], ["169.254.169.254"], ["10.1.2.3"], ["93.184.216.34", "192.168.0.7"], ["::1"]],
)
def test_rejects_names_resolving_to_private_addresses(monkeypatch, resolved: list[str]) -> None:
    # A public-looking name that resolves (even partly) to a private address is refused.
    monkeypatch.setattr(safe_url, "resolve_host", lambda host: resolved)
    with pytest.raises(ApiError) as exc:
        safe_url.check_public_url("https://metadata.example.com/a.mp3")
    assert exc.value.code == "unsupported_url"


def test_accepts_public_addresses() -> None:
    safe_url.check_public_url("https://archive.org/download/x/y_64kb.mp3")
    safe_url.check_public_url("http://93.184.216.34/a.mp3")
    safe_url.check_public_url("https://[2606:2800:220:1:248:1893:25c8:1946]/a.mp3")


def test_unresolvable_name_is_refused(monkeypatch) -> None:
    def boom(host: str) -> list[str]:
        raise ApiError("unsupported_url", f"host {host!r} does not resolve", 400)

    monkeypatch.setattr(safe_url, "resolve_host", boom)
    with pytest.raises(ApiError):
        safe_url.check_public_url("https://no-such-host.invalid/a.mp3")


def _hops(monkeypatch, answers: list[tuple[int, dict[str, str]]]) -> list[str]:
    """Replace the network with a scripted sequence of (status, headers); returns the urls asked."""
    asked: list[str] = []

    def fake_head(url: str, timeout: float):
        asked.append(url)
        status, headers = answers[len(asked) - 1]
        return status, headers, url

    monkeypatch.setattr(safe_url, "_head", fake_head)
    return asked


def test_redirect_to_private_address_is_refused(monkeypatch, settings: Settings) -> None:
    asked = _hops(monkeypatch, [(302, {"location": "http://169.254.169.254/latest/meta-data/"})])
    with pytest.raises(ApiError) as exc:
        safe_url.resolve_direct("https://files.example.com/a.mp3", settings)
    assert exc.value.code == "unsupported_url"
    assert asked == ["https://files.example.com/a.mp3"]  # the metadata address was never opened


def test_redirect_to_public_address_is_followed(monkeypatch, settings: Settings) -> None:
    asked = _hops(
        monkeypatch,
        [
            (302, {"location": "/cdn/a.mp3"}),
            (301, {"location": "https://cdn.example.net/a.mp3"}),
            (200, {"content-length": "1234", "content-type": "audio/mpeg"}),
        ],
    )
    final, size = safe_url.resolve_direct("https://files.example.com/a.mp3", settings)
    assert (final, size) == ("https://cdn.example.net/a.mp3", 1234)
    assert asked == [
        "https://files.example.com/a.mp3",
        "https://files.example.com/cdn/a.mp3",
        "https://cdn.example.net/a.mp3",
    ]


def test_too_many_redirects(monkeypatch, settings: Settings) -> None:
    _hops(monkeypatch, [(302, {"location": "https://files.example.com/loop"})] * 10)
    with pytest.raises(ApiError) as exc:
        safe_url.resolve_direct("https://files.example.com/a.mp3", settings)
    assert "redirects" in exc.value.message


def test_size_cap_before_download(monkeypatch, settings: Settings) -> None:
    _hops(monkeypatch, [(200, {"content-length": str(settings.upload_max_mb * 1024 * 1024 + 1)})])
    with pytest.raises(ApiError) as exc:
        safe_url.resolve_direct("https://files.example.com/big.mp4", settings)
    assert (exc.value.code, exc.value.status_code) == ("file_too_large", 413)


GENERIC_MP3 = {
    "extractor": "generic",
    "id": "nice_people_bunner_wsc_64kb",
    "title": "nice_people_bunner_wsc_64kb",
    "duration": None,
    "subtitles": {},
    "automatic_captions": {},
}


def test_probe_direct_file_gets_duration_from_ffprobe(
    client: TestClient, auth_headers, monkeypatch, settings: Settings
) -> None:
    monkeypatch.setattr(ytdlp, "dump_info", lambda _u, _s: GENERIC_MP3)
    seen: dict[str, str] = {}

    def fake_resolve(url: str, _settings):
        seen["resolved"] = url
        return "https://ia800.us.archive.org/nice_people_bunner_wsc_64kb.mp3", 9_500_000

    def fake_probe_url(url: str, _settings):
        seen["probed"] = url
        return MediaInfo(duration_sec=1187.2, format_name="mp3", has_audio=True, has_video=False)

    monkeypatch.setattr(safe_url, "resolve_direct", fake_resolve)
    monkeypatch.setattr(ffprobe, "probe_url", fake_probe_url)
    resp = client.post(
        "/probe",
        json={
            "url": "https://archive.org/download/stories_001_librivox/nice_people_bunner_wsc_64kb.mp3"
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["platform"] == "generic"
    assert body["duration_sec"] == pytest.approx(1187.2)
    assert body["recommended"] == "transcribe"
    assert seen["probed"] == "https://ia800.us.archive.org/nice_people_bunner_wsc_64kb.mp3"
    # yt-dlp will download from the checked final url, not from the original one
    from app.services import storage

    meta = storage.read_meta(settings, body["source_id"])
    assert meta is not None and meta.download_url == seen["probed"]


def test_probe_refuses_private_link_before_ytdlp(client: TestClient, auth_headers, monkeypatch):
    called = []
    monkeypatch.setattr(ytdlp, "dump_info", lambda u, s: called.append(u) or GENERIC_MP3)
    resp = client.post("/probe", json={"url": "http://127.0.0.1:8000/health"}, headers=auth_headers)
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "unsupported_url"
    assert called == []


def test_probe_direct_file_without_audio_is_refused(client: TestClient, auth_headers, monkeypatch):
    monkeypatch.setattr(ytdlp, "dump_info", lambda _u, _s: GENERIC_MP3)
    monkeypatch.setattr(safe_url, "resolve_direct", lambda u, s: (u, 100))
    monkeypatch.setattr(
        ffprobe,
        "probe_url",
        lambda u, s: MediaInfo(
            duration_sec=3.0, format_name="png", has_audio=False, has_video=False
        ),
    )
    resp = client.post("/probe", json={"url": "https://example.com/a.png"}, headers=auth_headers)
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "unsupported_url"


def test_build_probe_response_keeps_none_duration_for_generic() -> None:
    assert probe.build_probe_response(GENERIC_MP3).duration_sec is None
