"""Live channel viewing: transcodes a channel's raw MPEG-2 tuner stream to
H.264/AAC via a local `ffmpeg` subprocess so it's playable in-browser, and
hands a channel's raw stream off to a native player app ("open in external
player") via a tiny `.m3u` playlist — no browser can decode raw MPEG-2
itself, and a bare link to the MPEG-TS URL just downloads an opaque blob.

Native clients whose own platform *can* decode raw MPEG-2/MPEG-TS (unlike a
browser) can pass `?direct=true` on the stream endpoint to skip ffmpeg
entirely and get the tuner's bytes proxied through unmodified.

Teardown today is disconnect-driven (`request.is_disconnected()` polled in
the streaming generator) — the stream-session/heartbeat contract native
clients need is a later addition; see the plan.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import shlex
import shutil
import time
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import StreamingResponse

from app import hls_streaming, hwaccel, transcoding
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
# Backstop for a connection that never delivers a clean close/reset (e.g. a
# mobile client suspended without tearing down its socket): if the response
# generator hasn't made forward progress in this long, assume the peer is
# gone and release the tuner ourselves rather than waiting on it forever.
# Matches WATCH_HEARTBEAT_TIMEOUT_SECONDS/DVREngine.tick's cadence so this
# path degrades the same way the watch-session path does.
_STALL_TIMEOUT_SECONDS = 60
_STALL_CHECK_INTERVAL_SECONDS = 10


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


async def _stall_watchdog(
    process: asyncio.subprocess.Process,
    last_activity: list[float],
    channel_number: str,
) -> None:
    """Kill `process` if `body()`'s loop stops making progress for too long.

    `request.is_disconnected()` depends on the ASGI server actually noticing
    the socket is gone, which requires a clean close/reset - a connection
    that's silently gone (app suspended without tearing down its socket, a
    send that blocks forever on a dead peer) can otherwise hold the tuner
    indefinitely. This runs as an independent task specifically because a
    stalled `yield` inside `body()` would block that generator itself from
    ever reaching its own disconnect check again.
    """
    while True:
        await asyncio.sleep(_STALL_CHECK_INTERVAL_SECONDS)
        if process.returncode is not None:
            return
        if time.monotonic() - last_activity[0] > _STALL_TIMEOUT_SECONDS:
            logger.warning(
                "Channel %s: stream stalled (no activity for %ss); releasing tuner",
                channel_number,
                _STALL_TIMEOUT_SECONDS,
            )
            await terminate_process(process, timeout=_FFMPEG_TERMINATE_TIMEOUT_SECONDS)
            return


_DIRECT_CONNECT_TIMEOUT_SECONDS = 10
_DIRECT_STALL_TIMEOUT_SECONDS = 60
_DIRECT_STALL_CHECK_INTERVAL_SECONDS = 10


async def _proxy_raw_stream(raw_url: str, channel_number: str, request: Request) -> StreamingResponse:
    """Direct-play passthrough for `?direct=true`: forwards the tuner's raw
    MPEG-2/MPEG-TS bytes unmodified for clients whose own platform can
    decode them - no ffmpeg subprocess is involved, so tuner release on
    disconnect/stall is handled directly against the httpx connection
    instead of via `terminate_process`.
    """
    client = httpx.AsyncClient(timeout=httpx.Timeout(_DIRECT_CONNECT_TIMEOUT_SECONDS, read=None))
    try:
        resp = await client.send(client.build_request("GET", raw_url), stream=True)
    except httpx.HTTPError as exc:
        await client.aclose()
        raise HTTPException(status_code=502, detail=f"Could not reach tuner: {exc}") from exc

    if resp.status_code >= 400:
        await resp.aclose()
        await client.aclose()
        raise HTTPException(status_code=502, detail=f"Tuner rejected stream request (HTTP {resp.status_code})")

    logger.info("Channel %s: direct passthrough (no transcode)", channel_number)

    last_activity = [time.monotonic()]

    async def watchdog() -> None:
        while True:
            await asyncio.sleep(_DIRECT_STALL_CHECK_INTERVAL_SECONDS)
            if time.monotonic() - last_activity[0] > _DIRECT_STALL_TIMEOUT_SECONDS:
                logger.warning(
                    "Channel %s: direct stream stalled (no activity for %ss); releasing tuner",
                    channel_number,
                    _DIRECT_STALL_TIMEOUT_SECONDS,
                )
                await resp.aclose()
                await client.aclose()
                return

    watchdog_task = asyncio.create_task(watchdog())

    async def body():
        chunks = resp.aiter_bytes(STREAM_CHUNK_BYTES)
        try:
            while True:
                last_activity[0] = time.monotonic()
                if await request.is_disconnected():
                    break
                try:
                    chunk = await asyncio.wait_for(chunks.__anext__(), timeout=_DISCONNECT_POLL_INTERVAL_SECONDS)
                except TimeoutError:
                    continue
                except StopAsyncIteration:
                    break
                except Exception:
                    # The watchdog above closed `resp` out from under us.
                    break
                yield chunk
        finally:
            watchdog_task.cancel()
            await resp.aclose()
            await client.aclose()

    return StreamingResponse(body(), media_type="video/mp2t")


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
async def stream_channel(channel_number: str, request: Request, direct: bool = False):
    settings = await get_hdhomerun_settings()
    if not hdhomerun_client.is_tuner_configured(settings):
        raise HTTPException(status_code=404, detail="Tuner not configured")

    # channel_number is never taken from a client-supplied URL — only used
    # to build the tuner's own stream URL server-side, from settings the
    # user already saved. Reconstructing it this way (rather than trusting a
    # client-passed URL) avoids turning this into an open proxy.
    raw_url = hdhomerun_client.raw_stream_url(settings, channel_number)

    if direct:
        return await _proxy_raw_stream(raw_url, channel_number, request)

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

    last_activity = [time.monotonic()]
    watchdog_task = asyncio.create_task(_stall_watchdog(process, last_activity, channel_number))

    async def body():
        try:
            yield first_chunk
            while True:
                # Mark progress once per loop iteration (not tied to a
                # successful read/yield) so a `yield` that never returns
                # control here - because the send it's waiting on is stuck -
                # is exactly what makes this go stale for the watchdog above.
                last_activity[0] = time.monotonic()
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
            watchdog_task.cancel()
            # Run on an independent task rather than awaiting inline: if
            # this generator is being torn down because its own task was
            # cancelled (the client-disconnect case), awaiting anything
            # directly here would be cancelled too, before ffmpeg is
            # actually reaped and the tuner released.
            run_in_background(terminate_process(process, timeout=_FFMPEG_TERMINATE_TIMEOUT_SECONDS))

    return StreamingResponse(body(), media_type="video/mp2t")


@router.post("/hls/{channel_number}")
async def stream_channel_hls(channel_number: str):
    """Busy-tuner-fallback HLS entry point for native (Apple) clients — the
    primary playback path is `/api/dvr/recording-stream-hls` (every live
    watch goes through a builtin-DVR capture first); this exists for the
    "official HDHomeRun DVR" / tuner-busy fallback that `/stream/{channel}`
    already serves to the web frontend as raw mpegts.
    """
    settings = await get_hdhomerun_settings()
    if not hdhomerun_client.is_tuner_configured(settings):
        raise HTTPException(status_code=404, detail="Tuner not configured")

    raw_url = hdhomerun_client.raw_stream_url(settings, channel_number)
    session_id, tmp_dir = hls_streaming.allocate_session_dir()
    try:
        ffmpeg_args = transcoding.build_ffmpeg_args(
            settings,
            raw_url,
            output_format="hls",
            hls_playlist_path=hls_streaming.playlist_path(tmp_dir),
            hls_segment_pattern=hls_streaming.segment_pattern(tmp_dir),
        )
    except transcoding.InvalidCustomFfmpegArgsError as exc:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        session = await hls_streaming.create_session(
            session_id,
            tmp_dir,
            ffmpeg_args,
            label=f"channel {channel_number}",
            min_segments=hls_streaming.HLS_READY_MIN_SEGMENTS,
        )
    except hls_streaming.HLSStartupError as exc:
        raise HTTPException(status_code=502, detail=exc.detail) from exc

    return {
        "session_id": session.session_id,
        "playlist_url": f"/api/hls/{session.session_id}/playlist.m3u8",
    }


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
