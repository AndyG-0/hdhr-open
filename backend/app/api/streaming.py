"""Live channel viewing: transcodes a channel's raw MPEG-2 tuner stream to
H.264/AAC via a local `ffmpeg` subprocess so it's playable in-browser, and
hands a channel's raw stream off to a native player app ("open in external
player") via a tiny `.m3u` playlist — no browser can decode raw MPEG-2
itself, and a bare link to the MPEG-TS URL just downloads an opaque blob.

Teardown today is disconnect-driven (`request.is_disconnected()` polled in
the streaming generator) — the stream-session/heartbeat contract native
clients need is a later addition; see the plan.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import shlex
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import StreamingResponse

from app import hwaccel, transcoding
from app.api._hdhomerun_settings import get_hdhomerun_settings
from app.async_utils import drain_stderr_tail, run_in_background, terminate_process
from app.auth import get_current_admin, get_current_user
from app.integrations import hdhomerun_client
from app.subprocess_streaming import (
    DETAIL_REASON_CHARS,
    FFMPEG_NOT_FOUND_DETAIL,
    FFMPEG_STARTUP_TIMEOUT_SECONDS,
    STDERR_FLUSH_TIMEOUT_SECONDS,
    STDERR_TAIL_BYTES,
    STREAM_CHUNK_BYTES,
    build_ffmpeg_failure_detail,
    describe_ffmpeg_startup_failure,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/streaming", tags=["streaming"], dependencies=[Depends(get_current_user)])

_FFMPEG_TERMINATE_TIMEOUT_SECONDS = 5
_DISCONNECT_POLL_INTERVAL_SECONDS = 1
_FAILURE_PROBE_TIMEOUT_SECONDS = 15


@router.get("/transcode-presets")
async def transcode_presets():
    # input_args/output_args are exposed (not just label/description) so the
    # settings UI can render a live command preview as the user changes
    # hwaccel/custom_ffmpeg_args, before saving.
    return [
        {
            "id": preset_id,
            "label": preset.label,
            "description": preset.description,
            "input_args": preset.input_args,
            "output_args": preset.output_args,
            "hardware": preset.hardware,
        }
        for preset_id, preset in transcoding.TRANSCODE_PRESETS.items()
    ]


async def _describe_mid_stream_exit(
    process: asyncio.subprocess.Process,
    stderr_tail: bytearray,
    drain_done: asyncio.Event,
    channel_number: str,
) -> None:
    """Log a stream that started successfully and then died on its own."""
    with contextlib.suppress(TimeoutError):
        await asyncio.wait_for(process.wait(), timeout=STDERR_FLUSH_TIMEOUT_SECONDS)
    if process.returncode in (None, 0):
        return
    with contextlib.suppress(TimeoutError):
        await asyncio.wait_for(drain_done.wait(), timeout=STDERR_FLUSH_TIMEOUT_SECONDS)
    logger.warning(
        "Channel %s: ffmpeg exited with code %s mid-stream\nffmpeg output:\n%s",
        channel_number,
        process.returncode,
        bytes(stderr_tail).decode(errors="replace").strip() or "(none)",
    )


async def _probe_after_failure(settings: dict[str, Any]) -> dict[str, Any] | None:
    """Re-run the failed settings against a synthetic clip, or None if that couldn't be done.

    Separates "the GPU can't do this" from "the tuner was busy / the channel
    is dead", which the tuner-fed failure alone cannot distinguish. Bounded
    and never raising: this runs inside an already-failing request.
    """
    try:
        return await asyncio.wait_for(hwaccel.probe_transcode(settings), timeout=_FAILURE_PROBE_TIMEOUT_SECONDS)
    except TimeoutError:
        return None
    except Exception:
        logger.exception("Diagnostic test transcode failed to run")
        return None


@router.get("/stream/{channel_number}")
async def stream_channel(channel_number: str, request: Request):
    settings = await get_hdhomerun_settings()
    if not hdhomerun_client.is_tuner_configured(settings):
        raise HTTPException(status_code=404, detail="Tuner not configured")

    # channel_number is never taken from a client-supplied URL — only used
    # to build the tuner's own stream URL server-side, from settings the
    # user already saved. Reconstructing it this way (rather than trusting a
    # client-passed URL) avoids turning this into an open proxy.
    raw_url = hdhomerun_client.raw_stream_url(settings, channel_number)
    try:
        ffmpeg_args = transcoding.build_ffmpeg_args(settings, raw_url)
    except transcoding.InvalidCustomFfmpegArgsError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    preset_id = settings.get("hwaccel", transcoding.DEFAULT_PRESET)
    preset = transcoding.resolve_preset(preset_id)
    device = transcoding.resolve_device(settings)
    command = shlex.join(["ffmpeg", *ffmpeg_args])

    try:
        process = await asyncio.create_subprocess_exec(
            "ffmpeg",
            *ffmpeg_args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=FFMPEG_NOT_FOUND_DETAIL) from exc
    assert process.stdout is not None
    assert process.stderr is not None

    logger.info(
        "Channel %s: starting transcode (preset=%s, device=%s): %s",
        channel_number,
        preset_id,
        device,
        command,
    )

    stderr_tail = bytearray()
    drain_done = asyncio.Event()
    run_in_background(drain_stderr_tail(process.stderr, stderr_tail, drain_done, tail_bytes=STDERR_TAIL_BYTES))

    # A StreamingResponse commits its 200 status as soon as it starts, so any
    # ffmpeg failure (busy tuner, unreachable channel, bad input) has to
    # surface *before* that point. Give ffmpeg a startup window to either
    # produce its first chunk of output or fail.
    try:
        first_chunk = await asyncio.wait_for(
            process.stdout.read(STREAM_CHUNK_BYTES), timeout=FFMPEG_STARTUP_TIMEOUT_SECONDS
        )
    except TimeoutError:
        first_chunk = b""

    if not first_chunk:
        cause, reason = await describe_ffmpeg_startup_failure(
            process,
            stderr_tail,
            drain_done,
            startup_timeout=FFMPEG_STARTUP_TIMEOUT_SECONDS,
            flush_timeout=STDERR_FLUSH_TIMEOUT_SECONDS,
        )
        run_in_background(terminate_process(process, timeout=_FFMPEG_TERMINATE_TIMEOUT_SECONDS))
        logger.error(
            "Channel %s: %s (preset=%s, device=%s)\ncommand: %s\nffmpeg output:\n%s",
            channel_number,
            cause,
            preset_id,
            device,
            command,
            reason or "(none)",
        )

        # A hardware preset that fails at startup is the case where the raw
        # stderr is least likely to be self-explanatory - re-run the same
        # arguments against a synthetic MPEG-2 clip at verbose logging, so
        # the very first failure carries a real explanation.
        probe_hook = (lambda: _probe_after_failure(settings)) if preset.hardware else None
        detail = await build_ffmpeg_failure_detail(
            f"streaming channel {channel_number}",
            cause,
            reason,
            reason_chars=DETAIL_REASON_CHARS,
            probe_hook=probe_hook,
        )
        raise HTTPException(status_code=502, detail=detail)

    async def body():
        try:
            yield first_chunk
            while True:
                # Actively re-check for disconnect on a bounded read timeout
                # instead of relying solely on Starlette to cancel this
                # generator when the client goes away — that cancellation
                # has proven unreliable in practice.
                if await request.is_disconnected():
                    break
                try:
                    chunk = await asyncio.wait_for(
                        process.stdout.read(STREAM_CHUNK_BYTES), timeout=_DISCONNECT_POLL_INTERVAL_SECONDS
                    )
                except TimeoutError:
                    continue
                if not chunk:
                    # EOF on stdout: ffmpeg is done. A clean exit is just the
                    # tuner-side stream ending, but a non-zero code here is a
                    # stream that started fine and then broke.
                    await _describe_mid_stream_exit(process, stderr_tail, drain_done, channel_number)
                    break
                yield chunk
        finally:
            # Run on an independent task rather than awaiting inline: if
            # this generator is being torn down because its own task was
            # cancelled (the client-disconnect case), awaiting anything
            # directly here would be cancelled too, before ffmpeg is
            # actually reaped and the tuner released.
            run_in_background(terminate_process(process, timeout=_FFMPEG_TERMINATE_TIMEOUT_SECONDS))

    return StreamingResponse(body(), media_type="video/mp2t")


@router.get("/hwaccel-diagnostics", dependencies=[Depends(get_current_admin)])
async def hwaccel_diagnostics(device: str | None = None):
    """Probe every link in the hardware-acceleration chain and report back.

    Admin-only despite the router's user-level dependency: this exposes host
    hardware detail, device permissions and the backend's uid/gid.
    """
    settings = await get_hdhomerun_settings()
    report = await hwaccel.full_report(
        device or transcoding.resolve_device(settings),
        extra_settings={
            "hwaccel": settings.get("hwaccel", transcoding.DEFAULT_PRESET),
            "custom_ffmpeg_args": settings.get("custom_ffmpeg_args", ""),
        },
    )
    # Also to the log, so a user reporting a bug can paste `docker compose
    # logs backend` instead of having to re-run this against a cookie.
    logger.info(
        "Hardware acceleration diagnostics for %s\n%s",
        report["device"],
        "\n".join(report["summary"]) or "(no findings)",
    )
    return report


@router.get("/playlist/{channel_number}")
async def channel_playlist(channel_number: str):
    settings = await get_hdhomerun_settings()
    if not hdhomerun_client.is_tuner_configured(settings):
        raise HTTPException(status_code=404, detail="Tuner not configured")

    raw_url = hdhomerun_client.raw_stream_url(settings, channel_number)
    playlist = f"#EXTM3U\n#EXTINF:-1,{channel_number}\n{raw_url}\n"
    return Response(
        content=playlist,
        media_type="audio/x-mpegurl",
        headers={"Content-Disposition": f'inline; filename="{channel_number}.m3u"'},
    )
