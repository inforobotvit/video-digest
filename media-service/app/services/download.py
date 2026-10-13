"""POST /download: subtitles or audio for a probed source."""

import logging
import shutil
from pathlib import Path

from app.config import Settings
from app.errors import ApiError
from app.models import AudioArtifact, DownloadRequest, SourceMeta, SubtitlesArtifact
from app.services import ffmpeg, ffprobe, storage, subtitles, ytdlp
from app.services.upload import SOURCE_PREFIX

log = logging.getLogger(__name__)

RAW_DIR = "raw"
PLAYBACK_NAME = "playback.mp3"


def _require_meta(settings: Settings, source_id: str) -> SourceMeta:
    meta = storage.read_meta(settings, source_id)
    if meta is None:
        raise ApiError("source_not_found", f"unknown source_id {source_id}; call /probe first", 404)
    return meta


def audio_name(settings: Settings) -> str:
    return f"audio.{settings.audio_format}"


def _mb(path: Path) -> float:
    return round(path.stat().st_size / (1024 * 1024), 1)


def download(req: DownloadRequest, settings: Settings) -> SubtitlesArtifact | AudioArtifact:
    meta = _require_meta(settings, req.source_id)
    # One producer per source at a time: a concurrent request waits and gets the cached artifact.
    with storage.source_lock(settings, req.source_id):
        if req.mode == "audio":
            return _download_audio(meta, settings)
        assert req.lang is not None  # enforced by the request model
        return _download_subtitles(meta, req.mode == "subtitles_auto", req.lang, settings)


# --- subtitles ------------------------------------------------------------


def _download_subtitles(
    meta: SourceMeta, auto: bool, lang: str, settings: Settings
) -> SubtitlesArtifact:
    src_dir = storage.source_dir(settings, meta.source_id)
    target = src_dir / f"subs.{lang}.json"
    if target.is_file():
        segments = subtitles.load(target)
        return SubtitlesArtifact(path=str(target), segments=len(segments))
    if meta.kind != "url" or not meta.url:
        raise ApiError("subtitles_not_found", "uploaded files have no subtitles", 404)

    raw_dir = src_dir / RAW_DIR / "subs"
    shutil.rmtree(raw_dir, ignore_errors=True)
    try:
        raw = ytdlp.download_subtitles(meta.url, lang, auto, raw_dir, settings)
        if raw is None:
            kind = "automatic" if auto else "manual"
            raise ApiError("subtitles_not_found", f"no {kind} subtitles for lang={lang}", 404)
        segments = subtitles.parse_file(raw)
        raw_format = raw.suffix.lstrip(".")
    finally:
        _cleanup_raw(raw_dir)

    storage.dump_json(target, [s.model_dump() for s in segments])
    storage.record_operation(
        settings,
        meta,
        "download",
        params={"mode": "subtitles_auto" if auto else "subtitles_manual", "lang": lang},
        result={"path": str(target), "segments": len(segments), "raw_format": raw_format},
    )
    log.info(
        "subtitles done",
        extra={"source_id": meta.source_id, "lang": lang, "segments": len(segments)},
    )
    return SubtitlesArtifact(path=str(target), segments=len(segments))


# --- audio ----------------------------------------------------------------


def _download_audio(meta: SourceMeta, settings: Settings) -> AudioArtifact:
    src_dir = storage.source_dir(settings, meta.source_id)
    target = src_dir / audio_name(settings)
    playback = src_dir / PLAYBACK_NAME
    if target.is_file():
        info = ffprobe.probe_file(target, settings)
        return AudioArtifact(
            path=str(target),
            duration_sec=info.duration_sec or 0.0,
            size_mb=_mb(target),
            playback_path=str(playback) if playback.is_file() else None,
        )

    if meta.kind == "upload":
        source = _find_source(src_dir)
        make_playback = True
        cleanup: Path | None = None
    else:
        assert meta.url is not None
        raw_dir = src_dir / RAW_DIR / "audio"
        shutil.rmtree(raw_dir, ignore_errors=True)
        source = ytdlp.download_audio(meta.download_url or meta.url, raw_dir, settings)
        make_playback = False
        cleanup = raw_dir

    try:
        src_info = ffprobe.probe_file(source, settings)
        tmp_target = target.with_name(f".{target.name}.tmp{target.suffix}")
        ffmpeg.to_work_audio(source, tmp_target, settings)
        tmp_target.replace(target)

        if make_playback and not playback.is_file():
            tmp_playback = playback.with_name(f".{playback.name}.tmp.mp3")
            ffmpeg.to_playback(
                source, tmp_playback, stereo=src_info.audio_channels >= 2, settings=settings
            )
            tmp_playback.replace(playback)
    finally:
        if cleanup is not None:
            _cleanup_raw(cleanup)

    if meta.kind == "upload":
        # Only normalized tracks are kept; the original upload is gone from here on.
        source.unlink(missing_ok=True)

    info = ffprobe.probe_file(target, settings)
    result = AudioArtifact(
        path=str(target),
        duration_sec=info.duration_sec or src_info.duration_sec or 0.0,
        size_mb=_mb(target),
        playback_path=str(playback) if playback.is_file() else None,
    )
    storage.record_operation(
        settings,
        meta,
        "download",
        params={"mode": "audio"},
        result=result.model_dump() | {"source_deleted": meta.kind == "upload"},
    )
    log.info(
        "audio done",
        extra={
            "source_id": meta.source_id,
            "duration_sec": result.duration_sec,
            "size_mb": result.size_mb,
            "playback": result.playback_path is not None,
        },
    )
    return result


def _cleanup_raw(raw_subdir: Path) -> None:
    """Remove raw/<kind>/ and the raw/ parent once it is empty."""
    shutil.rmtree(raw_subdir, ignore_errors=True)
    parent = raw_subdir.parent
    if parent.name == RAW_DIR and parent.is_dir() and not any(parent.iterdir()):
        parent.rmdir()


def _find_source(src_dir: Path) -> Path:
    matches = sorted(src_dir.glob(f"{SOURCE_PREFIX}.*"))
    if not matches:
        raise ApiError(
            "source_not_found", "original upload already removed and no audio artifact exists", 410
        )
    return matches[0]
