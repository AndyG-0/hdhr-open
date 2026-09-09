"""Helpers shared across the media cache submodules: the on-disk cache
directory, the ffmpeg subprocess runner, and the WebVTT/SRT cue parsing and
cleanup helpers used by both the static (whole-file) and live caption paths.
"""

from __future__ import annotations

import re
from pathlib import Path

from app.async_utils import run_subprocess
from app.config import HDHOMERUN_MEDIA_CACHE_DIR

# Caption extraction decodes the whole file (no way to sample a prefix like
# the ffprobe detection pass does, since we don't know where in the
# recording captions will actually appear), at roughly 2 minutes of ffmpeg
# time per hour of content observed against real ATSC recordings - so this
# needs enough headroom for a multi-hour recording, not just a half-hour one.
_GENERATE_TIMEOUT_SECONDS = 600


def _cache_dir() -> Path:
    HDHOMERUN_MEDIA_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return HDHOMERUN_MEDIA_CACHE_DIR


async def _run_ffmpeg(argv: list[str], timeout: float | None = None) -> bool:
    # Read _GENERATE_TIMEOUT_SECONDS from the module namespace at call time
    # (not as a default-argument value bound at def time) so tests can
    # monkeypatch it.
    if timeout is None:
        timeout = _GENERATE_TIMEOUT_SECONDS
    result = await run_subprocess(argv, timeout=timeout, capture_stdout=False)
    if result.spawn_error is not None or result.timed_out:
        return False
    return result.returncode == 0


# FFmpeg's CEA-608 decoder (ccaption_dec.c) renders the "transparent space"
# special character - the doubled-width blank in CC's Special North American
# Character Set - as the literal ASS/SSA override sequence "\h" (or "\h\h"
# for the double-width form). The webvtt muxer has no concept of ASS
# override tags and passes decoded cue text through unchanged, so this
# leaks into displayed captions verbatim instead of rendering as a space.
_CC_TRANSPARENT_SPACE_RE = re.compile(r"(?:\\h)+")


def _strip_cc_control_artifacts(text: str) -> str:
    """Clean literal CEA-608 decoder escape artifacts (see
    `_CC_TRANSPARENT_SPACE_RE`) out of decoded cue text, collapsing each run
    down to a single ordinary space per line."""
    lines = []
    for line in text.split("\n"):
        cleaned = _CC_TRANSPARENT_SPACE_RE.sub(" ", line)
        cleaned = re.sub(r" {2,}", " ", cleaned).strip()
        lines.append(cleaned)
    return "\n".join(lines)


def _parse_vtt_timestamp(raw: str) -> float:
    parts = raw.strip().split(":")
    if len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
    elif len(parts) == 2:
        return int(parts[0]) * 60 + float(parts[1])
    elif len(parts) == 1:
        return float(parts[0])
    return 0.0


def _parse_vtt_block(block: str) -> tuple[float, float, str] | None:
    """Parse a single WebVTT cue block (no leading/trailing blank lines).
    Returns None for a non-cue block (the WEBVTT header, or a block missing
    a `-->` timing line) or one with malformed timestamps."""
    lines = [line for line in block.split("\n") if line.strip()]
    cue_line_index = next((i for i, line in enumerate(lines) if "-->" in line), None)
    if cue_line_index is None:
        return None
    start_raw, end_raw = (part.strip() for part in lines[cue_line_index].split("-->")[:2])
    text_lines = lines[cue_line_index + 1 :]
    if not text_lines:
        return None
    try:
        start = _parse_vtt_timestamp(start_raw)
        end = _parse_vtt_timestamp(end_raw.split(" ")[0])
    except ValueError:
        return None
    return (start, end, _strip_cc_control_artifacts("\n".join(text_lines)))


def _parse_vtt_cues(text: str) -> list[tuple[float, float, str]]:
    cues: list[tuple[float, float, str]] = []
    for block in text.replace("\r\n", "\n").split("\n\n"):
        cue = _parse_vtt_block(block)
        if cue is not None:
            cues.append(cue)
    return cues


_SRT_CUE_RE = re.compile(r"(\d\d):(\d\d):(\d\d),(\d\d\d) --> (\d\d):(\d\d):(\d\d),(\d\d\d)")
# `-1` on the ccextractor invocation already restricts decoding to CEA-608
# field 1/channel 1, so a CEA-708 cue shouldn't reach this parser at all. This
# `<font ...>` check is a defensive fallback, not the primary guard: it was
# originally relied on as the *only* way to tell a 708 cue from a 608 one
# (ccextractor decodes both by default, interleaved in one stdout stream),
# but real broadcast output showed plenty of 708 lines with no `<font>`
# wrapping at all, letting a second (e.g. Spanish SAP) caption track leak
# through as if it were the primary 608 text.
_SRT_FONT_TAG_RE = re.compile(r"</?font[^>]*>")


def _parse_srt_block(block: str) -> tuple[float, float, str] | None:
    """Parse a single SRT cue block (no leading/trailing blank lines) from
    ccextractor's `-out=srt -stdout` output. Returns None for a CEA-708 cue
    (see `_SRT_FONT_TAG_RE` - a defensive fallback, not the primary guard;
    see its comment) or a block missing a `-->` timing line."""
    if "<font" in block:
        return None
    match = _SRT_CUE_RE.search(block)
    if match is None:
        return None
    h1, m1, s1, ms1, h2, m2, s2, ms2 = match.groups()
    start = int(h1) * 3600 + int(m1) * 60 + int(s1) + int(ms1) / 1000
    end = int(h2) * 3600 + int(m2) * 60 + int(s2) + int(ms2) / 1000
    text_lines = [
        line for line in block.split("\n") if line.strip() and "-->" not in line and not line.strip().isdigit()
    ]
    if not text_lines:
        return None
    return (start, end, _strip_cc_control_artifacts("\n".join(text_lines)))


def _format_timestamp(seconds: float) -> str:
    hours, remainder = divmod(max(0.0, seconds), 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{int(hours):02d}:{int(minutes):02d}:{secs:06.3f}"


def _append_live_cues(output_path: Path, cues: list[tuple[float, float, str]]) -> None:
    is_new = not output_path.exists()
    lines: list[str] = []
    if is_new:
        lines.extend(["WEBVTT", ""])
    for start, end, text in cues:
        lines.append(f"{_format_timestamp(start)} --> {_format_timestamp(end)}")
        lines.append(text)
        lines.append("")
    with output_path.open("a") as f:
        f.write("\n".join(lines) + "\n")
