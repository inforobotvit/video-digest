"""yt-dlp wrapper: subprocess with timeout, stderr to log, error mapping."""

import json
import logging
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.config import Settings
from app.errors import ApiError

log = logging.getLogger(__name__)

# Order matters: the first matching pattern wins.
_ERROR_PATTERNS: list[tuple[str, str, int, str]] = [
    (
        r"sign in to confirm you.re not a bot|confirm your age|cookies.*(required|needed)",
        "bot_check",
        403,
        "YouTube asks to sign in; upload the file instead",
    ),
    (
        r"private video|video unavailable|is unavailable|has been removed|access restricted|"
        r"not available|members-only|is not available|deleted|does not exist|"
        r"login required|requires authentication|http error 403",
        "private_or_removed",
        404,
        "video is private, removed or not accessible",
    ),
    (
        r"unsupported url|is not a valid url|http error 404|unable to download webpage|"
        r"no video formats|unable to extract",
        "unsupported_url",
        400,
        "URL is not supported or does not point to a video",
    ),
]


@dataclass
class YtDlpResult:
    info: dict[str, Any]
    stderr: str


class YtDlpError(Exception):
    def __init__(self, returncode: int, stderr: str) -> None:
        super().__init__(f"yt-dlp exited with {returncode}")
        self.returncode = returncode
        self.stderr = stderr


def base_args(settings: Settings) -> list[str]:
    args = [settings.ytdlp_bin, "--no-warnings", "--no-progress", "--no-colors"]
    if settings.ytdlp_cookies_file:
        args += ["--cookies", str(settings.ytdlp_cookies_file)]
    if settings.ytdlp_proxy:
        args += ["--proxy", settings.ytdlp_proxy]
    return args


def run(args: list[str], timeout_sec: float) -> subprocess.CompletedProcess[str]:
    """Run yt-dlp; stderr always goes to the log. Raises YtDlpError on non-zero exit."""
    log.info("yt-dlp run", extra={"cmd": args[1:], "timeout_sec": timeout_sec})
    try:
        proc = subprocess.run(
            args, capture_output=True, text=True, timeout=timeout_sec, check=False
        )
    except FileNotFoundError as exc:
        raise ApiError("ytdlp_missing", "yt-dlp binary not found", 500) from exc
    except subprocess.TimeoutExpired as exc:
        log.error("yt-dlp timeout", extra={"cmd": args[1:], "timeout_sec": timeout_sec})
        raise ApiError(
            "ytdlp_timeout", f"yt-dlp did not finish in {timeout_sec:.0f}s", 504
        ) from exc
    stderr = proc.stderr.strip()
    if stderr:
        level = logging.ERROR if proc.returncode else logging.WARNING
        log.log(level, "yt-dlp stderr", extra={"returncode": proc.returncode, "stderr": stderr})
    if proc.returncode != 0:
        raise YtDlpError(proc.returncode, stderr)
    return proc


def map_error(stderr: str) -> ApiError:
    """Translate yt-dlp's stderr into a stable error code."""
    text = stderr.lower()
    for pattern, code, status, message in _ERROR_PATTERNS:
        if re.search(pattern, text):
            return ApiError(code, message, status)
    last_line = stderr.splitlines()[-1] if stderr else "unknown yt-dlp error"
    return ApiError("ytdlp_failed", last_line[:300], 502)


def dump_info(url: str, settings: Settings) -> dict[str, Any]:
    """Metadata only (-J): no media download. Playlists are not expanded."""
    args = base_args(settings) + [
        "--dump-single-json",
        "--skip-download",
        "--no-playlist",
        "--flat-playlist",
        "--",
        url,
    ]
    try:
        proc = run(args, settings.probe_timeout_sec)
    except YtDlpError as exc:
        raise map_error(exc.stderr) from exc
    try:
        info = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise ApiError("ytdlp_failed", "yt-dlp returned invalid JSON", 502) from exc
    if not isinstance(info, dict):
        raise ApiError("ytdlp_failed", "yt-dlp returned no metadata", 502)
    return info


def _common_download_args(settings: Settings, out_template: Path) -> list[str]:
    # --max-filesize: the upload cap; a direct link cannot pull more onto the disk than a file.
    return base_args(settings) + [
        "--no-playlist",
        "--no-overwrites",
        "--max-filesize",
        f"{settings.upload_max_mb}m",
        "-o",
        str(out_template),
    ]


def download_subtitles(
    url: str, lang: str, auto: bool, out_dir: Path, settings: Settings
) -> Path | None:
    """Fetch one subtitle track into out_dir. Returns the file or None if the lang is absent."""
    out_dir.mkdir(parents=True, exist_ok=True)
    args = _common_download_args(settings, out_dir / "subs.%(ext)s") + [
        "--skip-download",
        "--write-auto-subs" if auto else "--write-subs",
        "--sub-langs",
        f"{lang},{lang}-.*",  # 'ru' also matches 'ru-RU' / 'ru-orig'
        "--sub-format",
        "json3/vtt/srt/best",
        "--",
        url,
    ]
    try:
        run(args, settings.download_timeout_sec)
    except YtDlpError as exc:
        raise map_error(exc.stderr) from exc
    candidates = sorted(
        p for p in out_dir.iterdir() if p.suffix.lower() in (".json3", ".vtt", ".srt")
    )
    if not candidates:
        return None
    exact = [p for p in candidates if p.name.split(".")[1] == lang]
    return (exact or candidates)[0]


def download_audio(url: str, out_dir: Path, settings: Settings) -> Path:
    """Audio-only download (-f bestaudio), original container. Returns the file path."""
    out_dir.mkdir(parents=True, exist_ok=True)
    args = _common_download_args(settings, out_dir / "audio.%(ext)s") + [
        "-f",
        "bestaudio/best",
        "--",
        url,
    ]
    try:
        run(args, settings.download_timeout_sec)
    except YtDlpError as exc:
        raise map_error(exc.stderr) from exc
    files = [p for p in out_dir.iterdir() if p.is_file() and not p.name.endswith(".part")]
    if not files:
        raise ApiError("ytdlp_failed", "yt-dlp finished but produced no file", 502)
    return max(files, key=lambda p: p.stat().st_size)
