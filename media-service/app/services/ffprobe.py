"""ffprobe wrapper for local media files and, for direct links, files read over HTTP."""

import json
import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path

from app.config import Settings
from app.errors import ApiError

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class MediaInfo:
    duration_sec: float | None
    format_name: str
    has_audio: bool
    has_video: bool
    audio_channels: int = 0


def probe_file(path: Path, settings: Settings) -> MediaInfo:
    return _probe([str(path)], settings)


def probe_url(url: str, settings: Settings) -> MediaInfo:
    """Duration and streams of a file over HTTP: ffprobe reads only the headers it needs.

    The URL must have passed safe_url first; -rw_timeout bounds each network read.
    """
    rw_timeout_us = str(int(settings.direct_head_timeout_sec * 1_000_000))
    return _probe(["-rw_timeout", rw_timeout_us, url], settings)


def _probe(target: list[str], settings: Settings) -> MediaInfo:
    args = [
        settings.ffprobe_bin,
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        *target,
    ]
    try:
        proc = subprocess.run(
            args, capture_output=True, text=True, timeout=settings.ffprobe_timeout_sec, check=False
        )
    except FileNotFoundError as exc:
        raise ApiError("ffprobe_missing", "ffprobe binary not found", 500) from exc
    except subprocess.TimeoutExpired as exc:
        raise ApiError("ffprobe_timeout", "ffprobe timed out", 504) from exc
    if proc.returncode != 0:
        log.warning(
            "ffprobe failed",
            extra={
                "path": target[-1],
                "returncode": proc.returncode,
                "stderr": proc.stderr.strip(),
            },
        )
        raise ApiError("invalid_media", "file is not a readable audio/video container", 400)
    data = json.loads(proc.stdout or "{}")
    fmt = data.get("format", {})
    streams = data.get("streams", [])
    duration = fmt.get("duration")
    audio_streams = [s for s in streams if s.get("codec_type") == "audio"]
    return MediaInfo(
        duration_sec=float(duration) if duration else None,
        format_name=fmt.get("format_name", ""),
        has_audio=bool(audio_streams),
        has_video=any(s.get("codec_type") == "video" for s in streams),
        audio_channels=int(audio_streams[0].get("channels") or 0) if audio_streams else 0,
    )
