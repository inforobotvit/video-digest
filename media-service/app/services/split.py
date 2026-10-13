"""POST /split: cut the working audio track into STT-sized chunks at silences."""

import json
import logging
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from app.config import Settings
from app.errors import ApiError
from app.models import Chunk, SourceMeta, SplitRequest, SplitResponse
from app.services import download, ffmpeg, ffprobe, storage

log = logging.getLogger(__name__)

CHUNKS_DIR = "chunks"
MANIFEST_NAME = "manifest.json"
MIN_TAIL_SEC = 1.0  # a shorter remainder is merged into the previous chunk

_SILENCE_START_RE = re.compile(r"silence_start:\s*(-?[\d.]+)")
_SILENCE_END_RE = re.compile(r"silence_end:\s*(-?[\d.]+)")


@dataclass(frozen=True)
class Silence:
    start: float
    end: float

    @property
    def mid(self) -> float:
        return (self.start + self.end) / 2


def parse_silencedetect(stderr: str, duration: float) -> list[Silence]:
    """Pair silence_start / silence_end lines; an unterminated silence runs to the end."""
    silences: list[Silence] = []
    pending: float | None = None
    for line in stderr.splitlines():
        if m := _SILENCE_START_RE.search(line):
            pending = float(m.group(1))
        elif (m := _SILENCE_END_RE.search(line)) and pending is not None:
            silences.append(Silence(max(pending, 0.0), float(m.group(1))))
            pending = None
    if pending is not None:
        silences.append(Silence(max(pending, 0.0), duration))
    return silences


def detect_silences(audio: Path, duration: float, settings: Settings) -> list[Silence]:
    args = [
        settings.ffmpeg_bin,
        "-hide_banner",
        "-nostdin",
        "-i",
        str(audio),
        "-af",
        f"silencedetect=noise={settings.silence_noise_db}dB:d={settings.silence_min_sec}",
        "-f",
        "null",
        "-",
    ]
    log.info("ffmpeg run", extra={"cmd": args[1:]})
    try:
        proc = subprocess.run(
            args, capture_output=True, text=True, timeout=settings.download_timeout_sec, check=False
        )
    except FileNotFoundError as exc:
        raise ApiError("ffmpeg_missing", "ffmpeg binary not found", 500) from exc
    except subprocess.TimeoutExpired as exc:
        raise ApiError("download_timeout", "silencedetect timed out", 504) from exc
    if proc.returncode != 0:
        log.error("silencedetect failed", extra={"stderr": proc.stderr[-2000:]})
        raise ApiError("ffmpeg_failed", "silencedetect failed", 500)
    return parse_silencedetect(proc.stderr, duration)


def plan_boundaries(
    duration: float, chunk_sec: float, silences: list[Silence], window_sec: float
) -> list[float]:
    """Cut points (exclusive of 0 and duration).

    Each boundary aims at prev + chunk_sec and snaps to the middle of the silence closest
    to that target within +/- window_sec; with no silence there it stays exact.
    """
    cuts: list[float] = []
    prev = 0.0
    while duration - prev > chunk_sec + MIN_TAIL_SEC:
        target = prev + chunk_sec
        lo, hi = target - window_sec, target + window_sec
        best: float | None = None
        for sil in silences:
            if sil.end < lo or sil.start > hi:
                continue
            point = min(max(sil.mid, lo), hi)  # keep the cut inside the window
            if point <= prev + MIN_TAIL_SEC:
                continue
            if best is None or abs(point - target) < abs(best - target):
                best = point
        cut = round(best if best is not None else target, 3)
        cuts.append(cut)
        prev = cut
    return cuts


def max_chunk_sec_for_size(max_mb: float, bitrate: str) -> float:
    """Longest chunk that fits max_mb at a constant bitrate like '64k'."""
    match = re.fullmatch(r"(\d+(?:\.\d+)?)([kKmM]?)", bitrate.strip())
    if not match:
        raise ApiError("config_error", f"bad CHUNK_BITRATE: {bitrate!r}", 500)
    value, unit = float(match.group(1)), match.group(2).lower()
    bits_per_sec = value * {"": 1, "k": 1_000, "m": 1_000_000}[unit]
    return max_mb * 1024 * 1024 * 8 / bits_per_sec * 0.95  # 5% headroom for headers/padding


def split(req: SplitRequest, settings: Settings) -> SplitResponse:
    meta = storage.read_meta(settings, req.source_id)
    if meta is None:
        raise ApiError("source_not_found", f"unknown source_id {req.source_id}", 404)
    # Same lock as /download: two jobs on one source would otherwise rewrite chunks/ under each
    # other while the first job is already fetching the files; the waiter gets the manifest cache.
    with storage.source_lock(settings, req.source_id):
        return _split(meta, req, settings)


def _split(meta: SourceMeta, req: SplitRequest, settings: Settings) -> SplitResponse:
    src_dir = storage.source_dir(settings, req.source_id)
    audio = src_dir / download.audio_name(settings)
    if not audio.is_file():
        raise ApiError(
            "audio_not_found", "no audio track yet; call /download mode=audio first", 409
        )

    chunk_sec = float(req.chunk_sec or settings.chunk_sec_default)
    max_mb = float(req.max_mb or settings.chunk_max_mb_default)
    params = {"chunk_sec": chunk_sec, "max_mb": max_mb, "bitrate": settings.chunk_bitrate}

    chunks_dir = src_dir / CHUNKS_DIR
    manifest_path = chunks_dir / MANIFEST_NAME
    cached = _read_manifest(manifest_path, params)
    if cached is not None:
        return cached

    effective_chunk_sec = min(chunk_sec, max_chunk_sec_for_size(max_mb, settings.chunk_bitrate))
    info = ffprobe.probe_file(audio, settings)
    duration = info.duration_sec or 0.0
    if duration <= 0:
        raise ApiError("ffmpeg_failed", "cannot determine audio duration", 500)

    silences = detect_silences(audio, duration, settings)
    cuts = plan_boundaries(duration, effective_chunk_sec, silences, settings.split_window_sec)
    edges = [0.0, *cuts, round(duration, 3)]

    shutil.rmtree(chunks_dir, ignore_errors=True)
    chunks_dir.mkdir(parents=True)
    chunks: list[Chunk] = []
    for index, (start, end) in enumerate(zip(edges, edges[1:], strict=False)):
        path = chunks_dir / f"{index:03d}.mp3"
        _encode_chunk(audio, path, start, end, settings)
        size_mb = path.stat().st_size / (1024 * 1024)
        if size_mb > max_mb:
            raise ApiError(
                "chunk_too_large", f"chunk {index} is {size_mb:.1f} MB > max_mb={max_mb}", 500
            )
        chunks.append(Chunk(index=index, path=str(path), start=start, end=end))

    response = SplitResponse(chunks=chunks)
    manifest_path.write_text(
        json.dumps({"params": params, "chunks": response.model_dump()["chunks"]}, indent=2),
        encoding="utf-8",
    )
    storage.record_operation(
        settings,
        meta,
        "split",
        params=params,
        result={
            "chunks": len(chunks),
            "duration_sec": duration,
            "silences_found": len(silences),
            "snapped": sum(
                1 for i, c in enumerate(cuts) if abs(c - (i + 1) * effective_chunk_sec) > 1e-6
            ),
        },
    )
    log.info(
        "split done",
        extra={
            "source_id": req.source_id,
            "chunks": len(chunks),
            "duration_sec": duration,
            "silences_found": len(silences),
        },
    )
    return response


def _encode_chunk(audio: Path, path: Path, start: float, end: float, settings: Settings) -> None:
    # -ss/-to after -i: decode-then-trim, sample-accurate for wav and mp3 inputs alike.
    args = [
        settings.ffmpeg_bin,
        "-hide_banner",
        "-nostdin",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(audio),
        "-ss",
        f"{start:.3f}",
        "-to",
        f"{end:.3f}",
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-c:a",
        "libmp3lame",
        "-b:a",
        settings.chunk_bitrate,
        str(path),
    ]
    ffmpeg.run(args, settings.download_timeout_sec)


def _read_manifest(path: Path, params: dict[str, object]) -> SplitResponse | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("params") != params:
            return None
        response = SplitResponse.model_validate({"chunks": data["chunks"]})
    except (ValueError, KeyError):
        return None
    if all(Path(c.path).is_file() for c in response.chunks):
        return response
    return None
