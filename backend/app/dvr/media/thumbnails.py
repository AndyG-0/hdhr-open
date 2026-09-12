"""Scrub-bar thumbnail sprites and poster snapshots for completed DVR recordings."""

from __future__ import annotations

import contextlib
import math
from pathlib import Path

from app.dvr.media.shared import _format_timestamp, _run_ffmpeg, safe_cache_path

_SPRITE_COLUMNS = 10
_SPRITE_ROWS = 10
_SPRITE_TILE_WIDTH = 160
_SPRITE_TILE_HEIGHT = 90
_MIN_SPRITE_INTERVAL_SECONDS = 2.0


def _sprite_paths(recording_id: str) -> tuple[Path, Path]:
    return safe_cache_path(recording_id, ".jpg"), safe_cache_path(recording_id, ".thumbs.vtt")


def _build_sprite_vtt(jpg_filename: str, interval_seconds: float, tile_count: int, grid_columns: int) -> str:
    lines = ["WEBVTT", ""]
    for index in range(tile_count):
        start = index * interval_seconds
        end = (index + 1) * interval_seconds
        col = index % grid_columns
        row = index // grid_columns
        x = col * _SPRITE_TILE_WIDTH
        y = row * _SPRITE_TILE_HEIGHT
        lines.append(f"{_format_timestamp(start)} --> {_format_timestamp(end)}")
        lines.append(f"{jpg_filename}#xywh={x},{y},{_SPRITE_TILE_WIDTH},{_SPRITE_TILE_HEIGHT}")
        lines.append("")
    return "\n".join(lines)


async def generate_thumbnail_sprite(url: str, recording_id: str, duration_seconds: float) -> tuple[Path, Path] | None:
    """The cached (sprite JPEG, cue VTT) pair for `recording_id`, generating first if needed.

    A single `_SPRITE_COLUMNS`x`_SPRITE_ROWS` grid is spread evenly across
    the whole recording (interval adapts to duration) rather than sampling
    at a fixed interval, so a long recording doesn't lose thumbnail
    coverage past the first few minutes.
    """
    try:
        jpg_path, vtt_path = _sprite_paths(recording_id)
    except ValueError:
        return None
    if jpg_path.exists() and vtt_path.exists():
        return jpg_path, vtt_path

    if duration_seconds <= 0:
        return None

    tile_count = _SPRITE_COLUMNS * _SPRITE_ROWS
    interval_seconds = max(_MIN_SPRITE_INTERVAL_SECONDS, duration_seconds / tile_count)
    actual_tile_count = min(tile_count, max(1, math.ceil(duration_seconds / interval_seconds)))

    # The tile filter's WxH area is sized for the worst case (a long
    # recording sampled down to the full grid). A short recording samples
    # far fewer frames than that, and the filter only ever emits an output
    # frame once it's buffered a full W*H input frames — so a fixed
    # _SPRITE_COLUMNS x _SPRITE_ROWS area would silently produce nothing for
    # anything shorter than that. Size the grid to what's actually sampled,
    # and cap nb_frames to the same count so the filter flushes as soon as
    # those frames arrive instead of waiting for a full grid.
    grid_columns = min(_SPRITE_COLUMNS, actual_tile_count)
    grid_rows = math.ceil(actual_tile_count / grid_columns)

    tmp_jpg = jpg_path.with_name(f"{jpg_path.name}.tmp")
    argv = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        url,
        "-vf",
        (
            f"fps=1/{interval_seconds},scale={_SPRITE_TILE_WIDTH}:{_SPRITE_TILE_HEIGHT},"
            f"tile={grid_columns}x{grid_rows}:nb_frames={actual_tile_count}"
        ),
        "-frames:v",
        "1",
        "-q:v",
        "4",
        "-f",
        "image2",
        "-y",
        str(tmp_jpg),
    ]
    ok = await _run_ffmpeg(argv)
    if not ok or not tmp_jpg.exists():
        with contextlib.suppress(FileNotFoundError):
            tmp_jpg.unlink()
        return None

    tmp_jpg.replace(jpg_path)
    vtt_path.write_text(_build_sprite_vtt(jpg_path.name, interval_seconds, actual_tile_count, grid_columns))
    return jpg_path, vtt_path


def _poster_path(recording_id: str) -> Path:
    return safe_cache_path(recording_id, ".poster.jpg")


async def generate_poster(url: str, recording_id: str, offset_seconds: float = 10.0) -> Path | None:
    """Extract a representative snapshot frame from `url` for `recording_id`."""
    try:
        poster_path = _poster_path(recording_id)
    except ValueError:
        return None
    if poster_path.exists() and poster_path.stat().st_size > 0:
        return poster_path

    tmp_jpg = poster_path.with_name(f"{poster_path.name}.tmp")
    argv = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        str(offset_seconds),
        "-i",
        url,
        "-vf",
        "scale=640:-1",
        "-frames:v",
        "1",
        "-q:v",
        "3",
        "-f",
        "image2",
        "-y",
        str(tmp_jpg),
    ]
    ok = await _run_ffmpeg(argv, timeout=15)
    if not ok or not tmp_jpg.exists() or tmp_jpg.stat().st_size == 0:
        # Fallback to seeking from start (0s) if the offset was beyond duration
        argv_start = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            "0",
            "-i",
            url,
            "-vf",
            "scale=640:-1",
            "-frames:v",
            "1",
            "-q:v",
            "3",
            "-f",
            "image2",
            "-y",
            str(tmp_jpg),
        ]
        ok_start = await _run_ffmpeg(argv_start, timeout=15)
        if not ok_start or not tmp_jpg.exists() or tmp_jpg.stat().st_size == 0:
            with contextlib.suppress(FileNotFoundError):
                tmp_jpg.unlink()
            return None

    tmp_jpg.replace(poster_path)
    return poster_path if poster_path.exists() and poster_path.stat().st_size > 0 else None
