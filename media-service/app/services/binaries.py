"""Version detection for external binaries (yt-dlp, ffmpeg)."""

import logging
import re
import subprocess
from dataclasses import dataclass

log = logging.getLogger(__name__)

# Standalone (PyInstaller) builds can take a while on cold start.
VERSION_TIMEOUT_SEC = 30


def _run_version(cmd: list[str]) -> str | None:
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=VERSION_TIMEOUT_SEC, check=False
        )
    except FileNotFoundError:
        log.warning("binary not found", extra={"cmd": cmd})
        return None
    except subprocess.TimeoutExpired:
        log.warning("version check timed out", extra={"cmd": cmd})
        return None
    if proc.returncode != 0:
        log.warning(
            "version check failed",
            extra={"cmd": cmd, "returncode": proc.returncode, "stderr": proc.stderr.strip()},
        )
        return None
    return proc.stdout.strip().splitlines()[0] if proc.stdout.strip() else None


def ytdlp_version(binary: str = "yt-dlp") -> str | None:
    return _run_version([binary, "--version"])


_EJS_RE = re.compile(r"yt_dlp_ejs-([\w.]+)")
_JS_RUNTIMES_RE = re.compile(r"JS runtimes:\s*(.+)")


def parse_ytdlp_debug(text: str) -> tuple[str | None, str | None]:
    """(ejs version, JS runtime) from yt-dlp's verbose header; the runtime is None for 'none'."""
    ejs = _EJS_RE.search(text)
    runtime = _JS_RUNTIMES_RE.search(text)
    runtime_value = runtime.group(1).strip() if runtime else None
    if runtime_value and runtime_value.lower() == "none":
        runtime_value = None
    return (ejs.group(1) if ejs else None, runtime_value)


def ytdlp_ejs_and_runtime(binary: str = "yt-dlp") -> tuple[str | None, str | None]:
    """yt-dlp prints its EJS version and the JS runtime it found in the verbose header;
    --list-impersonate-targets is the cheapest command printing it without the network."""
    try:
        proc = subprocess.run(
            [binary, "-v", "--list-impersonate-targets"],
            capture_output=True,
            text=True,
            timeout=VERSION_TIMEOUT_SEC,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return (None, None)
    return parse_ytdlp_debug(proc.stderr + proc.stdout)


_FFMPEG_RE = re.compile(r"ffmpeg version (\S+)")


def parse_ffmpeg_version(first_line: str) -> str | None:
    match = _FFMPEG_RE.search(first_line)
    return match.group(1) if match else None


def ffmpeg_version(binary: str = "ffmpeg") -> str | None:
    line = _run_version([binary, "-version"])
    return parse_ffmpeg_version(line) if line else None


@dataclass(frozen=True)
class BinaryVersions:
    ytdlp: str | None
    ffmpeg: str | None
    ejs: str | None = None
    js_runtime: str | None = None

    @property
    def all_present(self) -> bool:
        return bool(self.ytdlp and self.ffmpeg)


def detect_versions(ytdlp_bin: str = "yt-dlp", ffmpeg_bin: str = "ffmpeg") -> BinaryVersions:
    """Detected once at startup; binaries do not change while the container runs."""
    ejs, js_runtime = ytdlp_ejs_and_runtime(ytdlp_bin)
    versions = BinaryVersions(
        ytdlp=ytdlp_version(ytdlp_bin),
        ffmpeg=ffmpeg_version(ffmpeg_bin),
        ejs=ejs,
        js_runtime=js_runtime,
    )
    log.info(
        "binary versions",
        extra={
            "ytdlp": versions.ytdlp,
            "ffmpeg": versions.ffmpeg,
            "ejs": versions.ejs,
            "js_runtime": versions.js_runtime,
        },
    )
    return versions
