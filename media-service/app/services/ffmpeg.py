"""ffmpeg wrapper: transcode to the STT working track and to playback.mp3."""

import logging
import subprocess
from pathlib import Path

from app.config import Settings
from app.errors import ApiError

log = logging.getLogger(__name__)


def run(args: list[str], timeout_sec: float) -> None:
    log.info("ffmpeg run", extra={"cmd": args[1:]})
    try:
        proc = subprocess.run(
            args, capture_output=True, text=True, timeout=timeout_sec, check=False
        )
    except FileNotFoundError as exc:
        raise ApiError("ffmpeg_missing", "ffmpeg binary not found", 500) from exc
    except subprocess.TimeoutExpired as exc:
        log.error("ffmpeg timeout", extra={"cmd": args[1:], "timeout_sec": timeout_sec})
        raise ApiError(
            "download_timeout", f"ffmpeg did not finish in {timeout_sec:.0f}s", 504
        ) from exc
    stderr = proc.stderr.strip()
    if proc.returncode != 0:
        log.error("ffmpeg failed", extra={"returncode": proc.returncode, "stderr": stderr[-2000:]})
        last = stderr.splitlines()[-1] if stderr else "unknown ffmpeg error"
        raise ApiError("ffmpeg_failed", last[:300], 500)
    if stderr:
        log.debug("ffmpeg stderr", extra={"stderr": stderr[-2000:]})


def _base(settings: Settings, src: Path) -> list[str]:
    return [
        settings.ffmpeg_bin,
        "-hide_banner",
        "-nostdin",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(src),
        "-vn",
        "-sn",
        "-dn",
    ]


def to_work_audio(src: Path, dst: Path, settings: Settings) -> None:
    """Mono 16 kHz: wav (pcm_s16le) or mp3 at AUDIO_MP3_BITRATE."""
    args = _base(settings, src) + ["-ac", "1", "-ar", "16000"]
    if settings.audio_format == "mp3":
        args += ["-c:a", "libmp3lame", "-b:a", settings.audio_mp3_bitrate]
    else:
        args += ["-c:a", "pcm_s16le"]
    run(args + [str(dst)], settings.download_timeout_sec)


def to_playback(src: Path, dst: Path, stereo: bool, settings: Settings) -> None:
    """44.1 kHz mp3 for the in-page player; stereo only if the source had it."""
    args = _base(settings, src) + [
        "-ac",
        "2" if stereo else "1",
        "-ar",
        "44100",
        "-c:a",
        "libmp3lame",
        "-b:a",
        settings.playback_bitrate,
        str(dst),
    ]
    run(args, settings.download_timeout_sec)
