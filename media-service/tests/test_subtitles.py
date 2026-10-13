import json

import pytest

from app.models import Segment
from app.services import subtitles

JSON3_MANUAL = json.dumps(
    {
        "events": [
            {"tStartMs": 1360, "dDurationMs": 1680, "segs": [{"utf8": "[♪♪♪]"}]},
            {
                "tStartMs": 22640,
                "dDurationMs": 4320,
                "segs": [{"utf8": "♪ You know the rules\nand so do I ♪"}],
            },
        ]
    }
)

JSON3_AUTO = json.dumps(
    {
        "events": [
            {"tStartMs": 0, "dDurationMs": 211879, "id": 1},  # window definition, no text
            {"tStartMs": 320, "dDurationMs": 14260, "segs": [{"utf8": "[Music]"}]},
            {"tStartMs": 18790, "aAppend": 1, "segs": [{"utf8": "\n"}]},
            {
                "tStartMs": 18800,
                "dDurationMs": 7160,
                "segs": [
                    {"utf8": "We're"},
                    {"utf8": " no", "tOffsetMs": 239},
                    {"utf8": " strangers", "tOffsetMs": 559},
                ],
            },
        ]
    }
)

VTT = """﻿WEBVTT
Kind: captions
Language: en

NOTE this is a comment

00:00:01.000 --> 00:00:03.500 align:start position:0%
<c.colorE5E5E5>Hello</c> <00:00:02.000>world

2
00:01:02.250 --> 00:01:04.000
Second&nbsp;line
continues here
"""

SRT = """1
00:00:01,000 --> 00:00:03,500
Hello world

2
01:01:02,250 --> 01:01:04,000
<i>Second</i> line
"""


def test_parse_json3_manual() -> None:
    segs = subtitles.parse_json3(JSON3_MANUAL)
    assert segs == [
        Segment(start=1.36, end=3.04, text="[♪♪♪]"),
        Segment(start=22.64, end=26.96, text="♪ You know the rules and so do I ♪"),
    ]


def test_parse_json3_auto_joins_words_and_skips_appends() -> None:
    segs = subtitles.parse_json3(JSON3_AUTO)
    assert [s.text for s in segs] == ["[Music]", "We're no strangers"]
    assert segs[1].start == 18.8
    assert segs[1].end == pytest.approx(25.96)


def test_parse_vtt_strips_tags_and_headers() -> None:
    segs = subtitles.parse_vtt(VTT)
    assert segs == [
        Segment(start=1.0, end=3.5, text="Hello world"),
        Segment(start=62.25, end=64.0, text="Second line continues here"),
    ]


def test_parse_srt() -> None:
    segs = subtitles.parse_srt(SRT)
    assert segs == [
        Segment(start=1.0, end=3.5, text="Hello world"),
        Segment(start=3662.25, end=3664.0, text="Second line"),
    ]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("00:00:01.000", 1.0), ("01:02:03,450", 3723.45), ("02:03.5", 123.5), ("00:00:00.07", 0.07)],
)
def test_parse_timestamp(raw: str, expected: float) -> None:
    assert subtitles.parse_timestamp(raw) == pytest.approx(expected)


def test_normalize_sorts_and_merges_rolling_duplicates() -> None:
    segs = [
        Segment(start=5.0, end=7.0, text="same line"),
        Segment(start=2.0, end=4.0, text="first"),
        Segment(start=7.0, end=9.0, text="same line"),
        Segment(start=20.0, end=19.0, text="end before start"),
    ]
    out = subtitles.normalize(segs)
    assert out == [
        Segment(start=2.0, end=4.0, text="first"),
        Segment(start=5.0, end=9.0, text="same line"),
        Segment(start=20.0, end=20.0, text="end before start"),
    ]


def test_parse_file_dispatch_and_errors(tmp_path) -> None:
    (tmp_path / "x.srt").write_text(SRT, encoding="utf-8")
    assert len(subtitles.parse_file(tmp_path / "x.srt")) == 2
    (tmp_path / "x.json3").write_text("{not json", encoding="utf-8")
    with pytest.raises(Exception, match="cannot parse"):
        subtitles.parse_file(tmp_path / "x.json3")
    (tmp_path / "x.ass").write_text("", encoding="utf-8")
    with pytest.raises(Exception, match="unsupported subtitle format"):
        subtitles.parse_file(tmp_path / "x.ass")
