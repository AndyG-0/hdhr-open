from __future__ import annotations

from app.dvr.media import shared


def test_parse_vtt_timestamp_supports_various_formats():
    assert shared._parse_vtt_timestamp("00:00:01.000") == 1.0
    assert shared._parse_vtt_timestamp("01:02:03.456") == 3723.456
    assert shared._parse_vtt_timestamp("00:05.123") == 5.123
    assert shared._parse_vtt_timestamp("12:34.500") == 754.5
    assert shared._parse_vtt_timestamp("12.345") == 12.345


def test_parse_vtt_cues_parses_multiple_cues_and_skips_header():
    vtt = "\n".join(
        [
            "WEBVTT",
            "",
            "00:01.000 --> 00:03.500",
            "Hello there",
            "",
            "01:00:04.000 --> 01:00:06.000",
            "Multi-line",
            "cue text",
            "",
        ]
    )
    cues = shared._parse_vtt_cues(vtt)
    assert cues == [
        (1.0, 3.5, "Hello there"),
        (3604.0, 3606.0, "Multi-line\ncue text"),
    ]


def test_append_live_cues_writes_header_only_once(tmp_path):
    output_path = tmp_path / "rec1.live.vtt"
    shared._append_live_cues(output_path, [(0.0, 2.0, "First")])
    shared._append_live_cues(output_path, [(2.0, 4.0, "Second")])

    text = output_path.read_text()
    assert text.count("WEBVTT") == 1
    assert "First" in text
    assert "Second" in text


def test_parse_vtt_block_parses_single_cue():
    block = "00:00:05.000 --> 00:00:07.000\nHi"
    assert shared._parse_vtt_block(block) == (5.0, 7.0, "Hi")


def test_parse_vtt_block_returns_none_for_header_or_missing_timing():
    assert shared._parse_vtt_block("WEBVTT") is None
    assert shared._parse_vtt_block("just text, no arrow here") is None


def test_parse_vtt_block_strips_cc_transparent_space_artifacts():
    # ffmpeg's CEA-608 decoder renders the "transparent space" special
    # character as the literal ASS override sequence "\h" (doubled for the
    # double-width form); the webvtt muxer passes it through unchanged.
    block = "00:00:05.000 --> 00:00:07.000\n\\hHello\\h\\hworld\\h"
    assert shared._parse_vtt_block(block) == (5.0, 7.0, "Hello world")


def test_strip_cc_control_artifacts_preserves_multiline_text():
    text = "\\hLine one\nLine\\htwo\\h\\h"
    assert shared._strip_cc_control_artifacts(text) == "Line one\nLine two"


def test_parse_srt_block_parses_single_cue():
    block = "1\n00:00:05,000 --> 00:00:07,000\nHi"
    assert shared._parse_srt_block(block) == (5.0, 7.0, "Hi")


def test_parse_srt_block_returns_none_for_missing_timing():
    assert shared._parse_srt_block("just text, no arrow here") is None


def test_parse_srt_block_skips_cea_708_font_tagged_track():
    # ccextractor emits CEA-708 alongside CEA-608 (when both exist in the
    # source) as font-tagged SRT blocks - only the plain 608 track is wanted
    # for live captions, so a font-tagged block is dropped entirely rather
    # than parsed with tags stripped.
    block = '1\n00:00:05,000 --> 00:00:07,000\n<font color="#aaaaaa">Hi</font>'
    assert shared._parse_srt_block(block) is None


def test_parse_srt_block_parses_multiline_cue():
    block = "1\n00:00:05,000 --> 00:00:07,000\nFirst line\nSecond line"
    assert shared._parse_srt_block(block) == (5.0, 7.0, "First line\nSecond line")
