"""`ffprobe` metadata for a finished HDHomeRun DVR recording.

Recordings have no Jellyfin-style sidecar metadata — everything the player
needs (duration, video/audio stream layout, whether ATSC closed captions
are embedded) has to come from actually probing the file. Only ever run
this against a *completed* recording: probing a still-growing DVR file
gives an unreliable/partial duration and stream list.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.async_utils import run_subprocess

_PROBE_TIMEOUT_SECONDS = 20

# Enough on-disk data for ffprobe to see full stream headers/PMT tables for
# an OTA capture; tiny relative to how large a recording will eventually get.
_MIN_IN_PROGRESS_PROBE_BYTES = 512 * 1024


async def probe(url: str) -> dict[str, Any] | None:
    """Duration/video/audio/caption metadata for `url`, or None on any failure.

    Never raises — a probe failure (ffprobe missing, the DVR/tuner
    unreachable, a malformed file) just means the player falls back to no
    duration/scrubbing/captions rather than a broken detail request.
    """
    argv = [
        "ffprobe",
        "-v",
        "error",
        # closed_captions is only populated when frames are actually decoded
        # (newer ffmpeg gates it behind -analyze_frames rather than deriving
        # it from stream headers), so ask for that explicitly. -read_intervals
        # caps it to the first 30s of video — ATSC CC data is embedded
        # consistently throughout a broadcast, so that's enough to detect it
        # without paying for a full-file decode (~30s+ for an hour-long
        # recording vs ~1s for a capped probe).
        "-analyze_frames",
        "-read_intervals",
        "%+30",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        url,
    ]
    result = await run_subprocess(argv, timeout=_PROBE_TIMEOUT_SECONDS)
    if result.spawn_error is not None or result.timed_out:
        return None

    if result.returncode != 0 or not result.stdout:
        return None

    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None

    return _parse(payload)


async def probe_in_progress(url: str, min_bytes: int = _MIN_IN_PROGRESS_PROBE_BYTES) -> dict[str, Any] | None:
    """Like probe(), but for a still-growing capture file.

    Refuses to probe until there's a minimum amount of data on disk - a
    fresh/near-empty file gives ffprobe nothing to look at, and drops
    duration_seconds from the result since it's meaningless against a
    partial file (callers should keep computing duration from wall-clock
    elapsed time instead, as they already do). Returns None if there isn't
    enough data yet or the underlying probe failed.
    """
    try:
        size = Path(url).stat().st_size
    except OSError:
        size = 0
    if size < min_bytes:
        return None

    result = await probe(url)
    if result is None:
        return None

    result = dict(result)
    result.pop("duration_seconds", None)
    return result


def _parse(payload: dict[str, Any]) -> dict[str, Any] | None:
    streams = payload.get("streams") or []
    fmt = payload.get("format") or {}

    video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio_streams = [s for s in streams if s.get("codec_type") == "audio"]

    duration_raw = fmt.get("duration") or (video_stream or {}).get("duration")
    try:
        duration_seconds = float(duration_raw) if duration_raw is not None else None
    except (TypeError, ValueError):
        duration_seconds = None

    video = None
    if video_stream is not None:
        video = {
            "codec": video_stream.get("codec_name"),
            "width": video_stream.get("width"),
            "height": video_stream.get("height"),
            "fps": _parse_frame_rate(video_stream.get("avg_frame_rate") or video_stream.get("r_frame_rate")),
        }

    audio = [
        {
            "index": index,
            "codec": stream.get("codec_name"),
            "channels": stream.get("channels"),
            "language": (stream.get("tags") or {}).get("language"),
        }
        for index, stream in enumerate(audio_streams)
    ]

    side_data = (video_stream or {}).get("side_data_list") or []
    has_side_data_cc = any(
        any(kw in str(sd.get("side_data_type", "")).lower() for kw in ("caption", "608", "708", "a53"))
        for sd in side_data
    )
    has_subtitle_stream = any(
        s.get("codec_type") == "subtitle"
        or s.get("codec_name") in ("eia_608", "cea_708", "subcc")
        or (s.get("disposition") or {}).get("captions") == 1
        for s in streams
    )
    has_captions = (
        bool((video_stream or {}).get("closed_captions"))
        or bool(((video_stream or {}).get("disposition") or {}).get("captions"))
        or has_side_data_cc
        or has_subtitle_stream
    )

    return {
        "duration_seconds": duration_seconds,
        "video": video,
        "audio": audio,
        "has_captions": has_captions,
    }


def _parse_frame_rate(raw: str | None) -> float | None:
    """ffprobe reports frame rate as a "num/den" fraction string, e.g. "30000/1001"."""
    if not raw:
        return None
    try:
        num, _, den = raw.partition("/")
        num_f = float(num)
        den_f = float(den) if den else 1.0
        if den_f == 0:
            return None
        return round(num_f / den_f, 3)
    except ValueError:
        return None
