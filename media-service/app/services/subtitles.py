"""Normalize subtitles (json3 / vtt / srt) into [{start, end, text}]."""

import json
import re
from pathlib import Path

from app.errors import ApiError
from app.models import Segment

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_TIMESTAMP_RE = re.compile(r"(?:(\d+):)?(\d{1,2}):(\d{2})[.,](\d{1,3})")
_CUE_LINE_RE = re.compile(r"^\s*(\S+)\s+-->\s+(\S+)")


def _clean_text(text: str) -> str:
    text = _TAG_RE.sub("", text)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<")
    text = text.replace("&gt;", ">").replace("&quot;", '"').replace("&#39;", "'")
    return _WS_RE.sub(" ", text).strip()


def parse_timestamp(value: str) -> float:
    match = _TIMESTAMP_RE.search(value)
    if not match:
        raise ValueError(f"bad timestamp: {value!r}")
    hours, minutes, seconds, frac = match.groups()
    millis = int(frac.ljust(3, "0"))
    return int(hours or 0) * 3600 + int(minutes) * 60 + int(seconds) + millis / 1000


def parse_json3(raw: str) -> list[Segment]:
    """YouTube json3. Auto captions carry word-level segs and '\\n' append events."""
    data = json.loads(raw)
    segments: list[Segment] = []
    for event in data.get("events", []):
        segs = event.get("segs")
        if not segs or event.get("aAppend"):
            continue
        text = _clean_text("".join(seg.get("utf8", "") for seg in segs))
        if not text:
            continue
        start = int(event.get("tStartMs", 0)) / 1000
        duration = int(event.get("dDurationMs") or 0) / 1000
        segments.append(Segment(start=start, end=start + duration, text=text))
    return segments


def parse_vtt(raw: str) -> list[Segment]:
    return _parse_cues(raw.lstrip("﻿"))


def parse_srt(raw: str) -> list[Segment]:
    return _parse_cues(raw.lstrip("﻿"))


def _parse_cues(raw: str) -> list[Segment]:
    """Shared for VTT and SRT: blocks separated by blank lines, one '-->' line per block."""
    segments: list[Segment] = []
    for block in re.split(r"\n\s*\n", raw.replace("\r\n", "\n").replace("\r", "\n")):
        lines = [line for line in block.split("\n") if line.strip()]
        cue_index = next((i for i, line in enumerate(lines) if "-->" in line), None)
        if cue_index is None:
            continue  # WEBVTT header, NOTE, STYLE, or SRT numeric-only block
        match = _CUE_LINE_RE.match(lines[cue_index])
        if not match:
            continue
        try:
            start, end = parse_timestamp(match.group(1)), parse_timestamp(match.group(2))
        except ValueError:
            continue
        text = _clean_text(" ".join(lines[cue_index + 1 :]))
        if text:
            segments.append(Segment(start=start, end=end, text=text))
    return segments


def normalize(segments: list[Segment]) -> list[Segment]:
    """Sort, fix end < start, drop exact repeats (auto captions 'roll' the same line)."""
    result: list[Segment] = []
    for seg in sorted(segments, key=lambda s: (s.start, s.end)):
        # Millisecond precision: avoids float noise like 21.880000000000003 in the output.
        start = round(seg.start, 3)
        end = round(max(seg.end, seg.start), 3)
        if result and result[-1].text == seg.text and start <= result[-1].end + 0.05:
            result[-1] = Segment(
                start=result[-1].start, end=max(result[-1].end, end), text=seg.text
            )
            continue
        result.append(Segment(start=start, end=end, text=seg.text))
    return result


_PARSERS = {".json3": parse_json3, ".vtt": parse_vtt, ".srt": parse_srt}


def parse_file(path: Path) -> list[Segment]:
    parser = _PARSERS.get(path.suffix.lower())
    if parser is None:
        raise ApiError("subtitles_format", f"unsupported subtitle format: {path.suffix}", 502)
    try:
        return normalize(parser(path.read_text(encoding="utf-8", errors="replace")))
    except (json.JSONDecodeError, ValueError) as exc:
        raise ApiError("subtitles_format", f"cannot parse {path.name}: {exc}", 502) from exc


def load(path: Path) -> list[Segment]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return [Segment.model_validate(item) for item in data]
