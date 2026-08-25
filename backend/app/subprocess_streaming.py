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
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger(__name__)

STREAM_CHUNK_BYTES = 64 * 1024
FFMPEG_STARTUP_TIMEOUT_SECONDS = 8
STDERR_TAIL_BYTES = 4000
STDERR_FLUSH_TIMEOUT_SECONDS = 2
DETAIL_REASON_CHARS = 500

FFMPEG_NOT_FOUND_DETAIL = (
    "ffmpeg is not installed or not on PATH for the backend process. "
    "If running in Docker/Podman, ffmpeg must be present in the backend image itself — "
    "installing it on the container host has no effect; rebuild the backend image."
)


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
