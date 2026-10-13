import pytest
from pydantic import TypeAdapter, ValidationError

from app.models import DownloadRequest, DownloadResponse, ProbeResponse, SplitRequest


def test_download_request_requires_lang_for_subtitles() -> None:
    with pytest.raises(ValidationError, match="lang is required"):
        DownloadRequest(source_id="a1b2c3d4e5f6", mode="subtitles_manual")


def test_download_request_audio_without_lang() -> None:
    req = DownloadRequest(source_id="a1b2c3d4e5f6", mode="audio")
    assert req.lang is None


def test_source_id_pattern_enforced() -> None:
    with pytest.raises(ValidationError):
        SplitRequest(source_id="not-a-hash")


def test_download_response_discriminates_on_artifact() -> None:
    adapter = TypeAdapter(DownloadResponse)
    subs = adapter.validate_python(
        {"artifact": "subtitles", "path": "/data/x/subs.ru.json", "segments": 842}
    )
    audio = adapter.validate_python(
        {"artifact": "audio", "path": "/data/x/audio.wav", "duration_sec": 3721, "size_mb": 118.3}
    )
    assert subs.segments == 842
    assert audio.size_mb == 118.3


def test_probe_response_matches_tz_example() -> None:
    resp = ProbeResponse(
        source_id="a1b2c3d4e5f6",
        platform="youtube",
        title="t",
        duration_sec=3721,
        subtitles={"manual": ["ru", "en"], "auto": ["ru"]},
        recommended="subtitles_manual",
    )
    assert set(resp.model_dump()) == {
        "source_id",
        "platform",
        "title",
        "duration_sec",
        "subtitles",
        "recommended",
        "language",
        "thumbnail_url",
    }
