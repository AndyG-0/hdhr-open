"""Shared building blocks for turning a failed-to-start ffmpeg subprocess into
a 502 with a real, ffmpeg-stderr-derived explanation.

Used by both live-channel streaming (api/streaming.py) and recording-stream
transcoding (api/dvr.py), which spawn ffmpeg the same way but differ in what
surrounds the spawn (hwaccel diagnostics, tail-follow pump teardown, stdin
wiring) - each call site still owns its own termination/cleanup/logging
around these building blocks; see the plan for why those aren't merged too.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger(__name__)

STREAM_CHUNK_BYTES = 64 * 1024
FFMPEG_STARTUP_TIMEOUT_SECONDS = 15
STDERR_TAIL_BYTES = 4000
STDERR_FLUSH_TIMEOUT_SECONDS = 2
DETAIL_REASON_CHARS = 500

FFMPEG_NOT_FOUND_DETAIL = (
    "ffmpeg is not installed or not on PATH for the backend process. "
    "If running in Docker/Podman, ffmpeg must be present in the backend image itself — "
    "installing it on the container host has no effect; rebuild the backend image."
)

# The web player (mpegts.js) throws away a failed stream request's response
# body, so it can't see the 502 detail these modules build - HDHomeRunPlayer's
# only way to read it is a plain fetch() re-request of the exact same URL
# right after the error (see frontend/src/lib/mpegts-player.ts). That re-fetch
# is only "cheap" - as its comment there assumes - if the backend actually
# fails fast the second time. It doesn't: the tuner-lock-timeout wait in
# api/dvr.py and the hwaccel diagnostic re-probe in api/streaming.py both cost
# many more seconds on their own, and a naive retry pays that cost twice. This
# cache makes an immediate repeat of the same failing request return the same
# (status, detail) instantly instead of redoing the slow work, restoring the
# "well under a second" assumption. Keyed by the full request URL, since
# that's exactly what the frontend re-requests.
_RECENT_FAILURE_TTL_SECONDS = 5
_recent_stream_failures: dict[str, tuple[float, int, str]] = {}


def record_stream_failure(key: str, status_code: int, detail: str) -> None:
    _recent_stream_failures[key] = (time.monotonic() + _RECENT_FAILURE_TTL_SECONDS, status_code, detail)


def get_recent_stream_failure(key: str) -> tuple[int, str] | None:
    entry = _recent_stream_failures.get(key)
    if entry is None:
        return None
    deadline, status_code, detail = entry
    if time.monotonic() >= deadline:
        del _recent_stream_failures[key]
        return None
    return status_code, detail


async def describe_ffmpeg_startup_failure(
    process: asyncio.subprocess.Process,
    stderr_tail: bytearray,
    drain_done: asyncio.Event,
    *,
    startup_timeout: float,
    flush_timeout: float,
) -> tuple[str, str]:
    """Why ffmpeg produced nothing: a one-line cause, and its stderr output."""
    with contextlib.suppress(TimeoutError):
        await asyncio.wait_for(drain_done.wait(), timeout=flush_timeout)
    with contextlib.suppress(TimeoutError):
        await asyncio.wait_for(process.wait(), timeout=flush_timeout)

    if process.returncode is not None:
        cause = f"ffmpeg exited with code {process.returncode} before producing any output"
    else:
        cause = f"ffmpeg produced no output within {startup_timeout}s and was still running"
    return cause, bytes(stderr_tail).decode(errors="replace").strip()


async def build_ffmpeg_failure_detail(
    context: str,
    cause: str,
    reason: str,
    *,
    reason_chars: int,
    probe_hook: Callable[[], Awaitable[dict[str, Any] | None]] | None = None,
) -> str:
    """The 502 detail text for a failed-to-start ffmpeg.

    `probe_hook`, when given, is awaited to run a hardware-acceleration
    diagnostic re-transcode of the same settings against a synthetic clip -
    separating "the GPU can't do this" from "the tuner was busy / the
    channel is dead", which the tuner-fed failure alone cannot distinguish.
    Only worth the extra latency for a hardware preset's failure, so callers
    pass None to skip it entirely.
    """
    detail = f"Could not start {context}: {cause}"
    if reason:
        detail += f". ffmpeg said: {reason[-reason_chars:]}"
        if "503" in reason or "All Tuners In Use" in reason or "Resource temporarily unavailable" in reason:
            detail += " (All hardware tuners appear to be in use on the HDHomeRun device)."

    if probe_hook is None:
        return detail

    probe = await probe_hook()
    if probe is None:
        return detail

    logger.error(
        "Diagnostic test transcode with the same settings %s\ncommand: %s\n%s",
        "succeeded (so the tuner or channel is the likely problem, not the GPU)" if probe["ok"] else "also failed",
        probe.get("command"),
        probe.get("output") or "(no output)",
    )
    if not probe["ok"] and probe.get("output"):
        detail += (
            " A test transcode with these same settings also failed, so this is a hardware-acceleration "
            "problem rather than a tuner problem. Run the hardware acceleration diagnostics for details."
        )
    elif probe["ok"]:
        detail += (
            " A test transcode with these same settings succeeded, so hardware acceleration is working — "
            "the tuner or this channel is the more likely problem."
        )
    return detail
