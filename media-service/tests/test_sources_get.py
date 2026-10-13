from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.services import ytdlp
from tests.test_probe import YT_WITH_SUBS

FIXTURE_WAV = Path(__file__).parent / "fixtures" / "tone-10s.wav"


def test_get_source_requires_key(client: TestClient, auth_headers, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(ytdlp, "dump_info", lambda _u, _s: YT_WITH_SUBS)
    sid = client.post(
        "/probe", json={"url": "https://youtu.be/jNQXAC9IVRw"}, headers=auth_headers
    ).json()["source_id"]

    assert client.get(f"/sources/{sid}").status_code == 401
    assert (
        client.get(f"/sources/{sid}", headers={"Authorization": "Bearer test-key"}).status_code
        == 200
    )

    body = client.get(f"/sources/{sid}", headers=auth_headers).json()
    assert body["source_id"] == sid
    assert body["kind"] == "url"
    assert body["url"] == "https://youtu.be/jNQXAC9IVRw"
    assert body["original_filename"] is None
    assert body["probe"]["title"] == "Me at the zoo"
    assert body["probe"]["recommended"] == "subtitles_manual"


def test_get_source_upload(client: TestClient, auth_headers) -> None:
    sid = client.post(
        "/upload",
        files={"file": ("Лекция 1.wav", FIXTURE_WAV.read_bytes(), "audio/wav")},
        headers=auth_headers,
    ).json()["source_id"]
    body = client.get(f"/sources/{sid}", headers=auth_headers).json()
    assert body["kind"] == "upload"
    assert body["url"] is None
    assert body["original_filename"] == "Лекция 1.wav"
    assert body["probe"]["platform"] == "upload"


def test_get_source_missing(client: TestClient, auth_headers) -> None:
    resp = client.get("/sources/0123456789ab", headers=auth_headers)
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "source_not_found"
