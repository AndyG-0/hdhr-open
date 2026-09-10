#!/usr/bin/env python3
"""CC-8 feasibility spike: measure how much latency a custom, real-time
CEA-608 decoder could recover versus the current ffmpeg movie/subcc->WebVTT
pipeline (backend/app/dvr/media_cache.py's _generate_captions_vtt_uncached /
_run_live_caption_process_once).

Standalone and read-only: does not touch media_cache.py or any production
path. Run against a real local recording with genuine embedded CEA-608
captions, so this needs no live tuner.

Method:
  1. Run today's production pipeline (same ffmpeg movie/subcc->webvtt
     command media_cache.py uses) against the recording and parse its cue
     timestamps.
  2. Decode the same recording frame-by-frame with PyAV, pull each frame's
     raw ATSC A53 CC byte pairs from side data (before ffmpeg's own
     roll-up decode+flush logic runs), and run a minimal CEA-608 field-1
     roll-up decoder that flushes a line the instant its own
     carriage-return control code is seen - not when the *next* line pushes
     it up.
  3. Match each decoded line's text against the corresponding WebVTT cue
     and report the latency delta between "when the raw decoder would have
     shown this line" and "when today's pipeline's cue for it starts".

Usage: uv run python scripts/cc8_realtime_caption_spike.py [path/to.ts] [duration_seconds]
"""

from __future__ import annotations

import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import av

DEFAULT_RECORDING = "recordings/MLB_Baseball_1788116400_661a1195.ts"
DEFAULT_DURATION_SECONDS = 120


# --- Step 1: today's production pipeline, for comparison -------------------


@dataclass
class Cue:
    start: float
    end: float
    lines: list[str]


_CUE_RE = re.compile(
    r"(\d\d):(\d\d):?(\d\d)?\.(\d\d\d) --> (\d\d):(\d\d):?(\d\d)?\.(\d\d\d)"
)


def _parse_ts(h: str, m: str, s: str | None, ms: str) -> float:
    # webvtt muxer here emits MM:SS.mmm (no hours), so the "h" group is
    # actually minutes and "m" is seconds - handled by treating a missing
    # third group as the two-field form.
    if s is None:
        minutes, seconds = int(h), int(m)
        return minutes * 60 + seconds + int(ms) / 1000
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000


@dataclass
class FlushedCue:
    cue: Cue
    flush_wall: float  # seconds since ffmpeg process launch, real-time-paced


def run_production_pipeline(recording: Path, duration: int) -> list[FlushedCue]:
    """Run today's production pipeline with input paced to real-time (-re),
    reading stdout incrementally so we can timestamp the wall-clock moment
    each cue is actually flushed - not just the timestamp embedded in its
    text. A cue's *embedded* start/end reflects when its text is on screen;
    the *flush* time reflects when ffmpeg's roll-up decoder actually made
    that text available to a live client, which is the number that matters
    for a live-latency comparison (this is what
    media_cache.py's `_record_lag_sample` measures against wall clock too).
    """
    escaped = str(recording).replace("\\", "\\\\").replace("'", "'\\''")
    argv = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "warning",
        "-re",
        "-f",
        "lavfi",
        "-i",
        f"movie='{escaped}'[out+subcc]",
        "-t",
        str(duration),
        "-map",
        "0:s:0",
        "-f",
        "webvtt",
        "-",
    ]
    start_wall = time.monotonic()
    proc = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0)
    assert proc.stdout is not None

    flushed: list[FlushedCue] = []
    buffer = ""
    while True:
        chunk = proc.stdout.read(256)
        if not chunk:
            break
        buffer += chunk.decode("utf-8", errors="replace")
        while "\n\n" in buffer:
            block, buffer = buffer.split("\n\n", 1)
            flush_wall = time.monotonic() - start_wall
            m = _CUE_RE.search(block)
            if not m:
                continue
            cue_start = _parse_ts(m.group(1), m.group(2), m.group(3), m.group(4))
            cue_end = _parse_ts(m.group(5), m.group(6), m.group(7), m.group(8))
            text_lines = [ln for ln in block.splitlines() if ln and "-->" not in ln]
            flushed.append(FlushedCue(cue=Cue(start=cue_start, end=cue_end, lines=text_lines), flush_wall=flush_wall))
    proc.wait(timeout=60)
    return flushed


# --- Step 2: minimal real-time CEA-608 field-1 roll-up decoder -------------
#
# Deliberately narrow scope for a feasibility spike, not a production
# decoder: field 1 / CC1 only, standard character set (no extended/
# double-byte glyphs), and only tracks carriage-return-triggered line
# completion - enough to measure "when did this line's text become fully
# available" without implementing full PAC row/column/style handling.

_STANDARD_CHARS = {
    0x27: "’",
    0x2A: "á",
    0x5C: "é",
    0x5E: "í",
    0x5F: "ó",
    0x60: "ú",
    0x7B: "ç",
    0x7C: "÷",
    0x7D: "Ñ",
    0x7E: "ñ",
    0x7F: "█",
}


def _strip_parity(b: int) -> int:
    return b & 0x7F


@dataclass
class LineEvent:
    text: str
    completed_at: float


@dataclass
class RollUpDecoder:
    buffer: list[str] = field(default_factory=list)
    last_control_pair: tuple[int, int] | None = None
    events: list[LineEvent] = field(default_factory=list)

    def feed(self, b1: int, b2: int, timestamp: float) -> None:
        c1, c2 = _strip_parity(b1), _strip_parity(b2)
        if c1 == 0 and c2 == 0:
            return  # padding

        if 0x10 <= c1 <= 0x1F:
            # Control codes (including PAC) are transmitted twice in a row
            # per spec; only act on the first of a repeated pair.
            if (c1, c2) == self.last_control_pair:
                self.last_control_pair = None
                return
            self.last_control_pair = (c1, c2)

            if c1 in (0x14, 0x1C) and c2 == 0x2D:  # carriage return
                text = "".join(self.buffer).strip()
                if text:
                    self.events.append(LineEvent(text=text, completed_at=timestamp))
                self.buffer.clear()
            elif c1 in (0x14, 0x1C) and c2 == 0x2C:  # erase displayed memory
                self.buffer.clear()
            # PAC / mode-setting codes otherwise ignored for this spike.
            return

        self.last_control_pair = None
        for code in (c1, c2):
            if code == 0x00:
                continue
            if 0x20 <= code <= 0x7F:
                self.buffer.append(_STANDARD_CHARS.get(code, chr(code)))


def decode_realtime(recording: Path, duration: int) -> list[LineEvent]:
    decoder = RollUpDecoder()
    container = av.open(str(recording))
    vstream = container.streams.video[0]
    # PyAV's frame.time is the raw PTS/time_base, not rebased to "seconds
    # since this stream started" - subtract the stream's own start_time (in
    # the same units ffmpeg's movie filter effectively normalizes its
    # webvtt output to, i.e. the first video frame == t=0) so the two
    # timelines are comparable.
    start_offset = (vstream.start_time or 0) * float(vstream.time_base)
    for frame in container.decode(vstream):
        rel_time = (frame.time or 0.0) - start_offset
        if rel_time > duration:
            break
        for item in frame.side_data:
            if str(item.type) != "Type.A53_CC":
                continue
            raw = bytes(item)
            for i in range(0, len(raw) - 2, 3):
                marker, b1, b2 = raw[i], raw[i + 1], raw[i + 2]
                cc_valid = (marker >> 2) & 0x01
                cc_type = marker & 0x03
                if cc_valid and cc_type == 0x00:  # NTSC field 1 (CC1/CC2)
                    decoder.feed(b1, b2, rel_time)
    container.close()
    return decoder.events


# --- Step 2b: ccextractor (Option B), same real-time-flush methodology -----

_SRT_CUE_RE = re.compile(
    r"(\d\d):(\d\d):(\d\d),(\d\d\d) --> (\d\d):(\d\d):(\d\d),(\d\d\d)"
)
_FONT_TAG_RE = re.compile(r"</?font[^>]*>")


def run_ccextractor_pipeline(recording: Path, duration: int) -> list[FlushedCue]:
    """Same real-time-paced, incrementally-read methodology as
    run_production_pipeline, but through ccextractor's own live/growing-file
    mode (-s) fed via an -re-paced ffmpeg remux over a pipe - the same way a
    live tuner capture would be tailed. Plain (non-CEA-708/font-tagged) SRT
    blocks are the CEA-608 track and are what we compare, matching the
    ffmpeg path above.
    """
    feeder = subprocess.Popen(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-re",
            "-i",
            str(recording),
            "-t",
            str(duration),
            "-c",
            "copy",
            "-f",
            "mpegts",
            "-",
        ],
        stdout=subprocess.PIPE,
    )
    start_wall = time.monotonic()
    proc = subprocess.Popen(
        ["ccextractor", "--stdin", "-s", "999999999", "-out=srt", "-stdout", "-o", "/dev/null"],
        stdin=feeder.stdout,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        bufsize=0,
    )
    assert feeder.stdout is not None and proc.stdout is not None
    feeder.stdout.close()  # let feeder receive SIGPIPE if ccextractor exits early

    flushed: list[FlushedCue] = []
    buffer = ""
    while True:
        chunk = proc.stdout.read(256)
        if not chunk:
            break
        buffer += chunk.decode("utf-8", errors="replace").replace("\r\n", "\n")
        while "\n\n" in buffer:
            block, buffer = buffer.split("\n\n", 1)
            flush_wall = time.monotonic() - start_wall
            if "<font" in block:
                continue  # CEA-708 track; we only compare the 608 track
            m = _SRT_CUE_RE.search(block)
            if not m:
                continue
            cue_start = _parse_ts(m.group(1), m.group(2), m.group(3), m.group(4))
            cue_end = _parse_ts(m.group(5), m.group(6), m.group(7), m.group(8))
            text_lines = [
                _FONT_TAG_RE.sub("", ln).strip()
                for ln in block.splitlines()
                if ln and "-->" not in ln and not ln.strip().isdigit()
            ]
            flushed.append(FlushedCue(cue=Cue(start=cue_start, end=cue_end, lines=text_lines), flush_wall=flush_wall))
    proc.wait(timeout=60)
    feeder.wait(timeout=60)
    return flushed


# --- Step 3: match + report -------------------------------------------------


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().upper())


def match_and_report(flushed: list[FlushedCue], events: list[LineEvent]) -> None:
    # A line is "new" the first time it appears anywhere in a cue's lines
    # (a 2-line cue's first line is carry-over from the previous cue, its
    # last line is what just got pushed up) - track flush time by first
    # sighting so carry-over re-appearances don't overwrite it.
    line_flush_wall: dict[str, float] = {}
    for fc in flushed:
        for ln in fc.cue.lines:
            key = normalize(ln)
            line_flush_wall.setdefault(key, fc.flush_wall)

    print(f"{'line (truncated)':50s}  {'raw-decode t':>12s}  {'ffmpeg flush t':>14s}  {'delta':>8s}")
    print("-" * 92)
    deltas: list[float] = []
    for event in events:
        key = normalize(event.text)
        flush_wall = line_flush_wall.get(key)
        if flush_wall is None:
            continue
        delta = flush_wall - event.completed_at
        deltas.append(delta)
        preview = event.text[:48]
        print(f"{preview:50s}  {event.completed_at:12.2f}  {flush_wall:14.2f}  {delta:8.2f}")

    if deltas:
        print("-" * 92)
        print(
            f"matched {len(deltas)} lines - avg delta {sum(deltas) / len(deltas):.2f}s, "
            f"min {min(deltas):.2f}s, max {max(deltas):.2f}s"
        )
        print(
            "delta = how much sooner the raw real-time decode completed a line "
            "than today's (real-time-paced) pipeline actually flushed the WebVTT "
            "cue containing it to its output pipe. Note: ffmpeg process "
            "startup/init adds a small (sub-second, typically) constant skew to "
            "all flush timestamps that the raw-decode side doesn't pay, so "
            "these deltas are a slight overestimate of the real win."
        )
    else:
        print("no lines matched between raw decode and ffmpeg cues - decoder logic needs a look")


def main() -> None:
    recording = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(DEFAULT_RECORDING)
    duration = int(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_DURATION_SECONDS

    print(f"Recording: {recording}  Duration window: {duration}s\n")

    print("Running today's production pipeline in real time (-re) to measure actual flush latency...")
    flushed = run_production_pipeline(recording, duration)
    print(f"  -> {len(flushed)} cues\n")

    print("Decoding raw A53 CC frame side-data with a minimal real-time roll-up decoder...")
    events = decode_realtime(recording, duration)
    print(f"  -> {len(events)} completed lines\n")

    print("=== ffmpeg movie/subcc -> webvtt (today's production pipeline) vs raw decode ===")
    match_and_report(flushed, events)

    print("\nRunning ccextractor's live/growing-file mode (-s), real-time-paced (Option B)...")
    try:
        ccext_flushed = run_ccextractor_pipeline(recording, duration)
        print(f"  -> {len(ccext_flushed)} CEA-608 cues\n")
        print("=== ccextractor (Option B) vs raw decode ===")
        match_and_report(ccext_flushed, events)
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        print(f"  -> skipped: {exc}")


if __name__ == "__main__":
    main()
