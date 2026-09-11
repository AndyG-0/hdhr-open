"""DVR recording playback: transcoded/HLS streaming, probe/caption/thumbnail
metadata for the player, and the in-memory caches that back them. Mounted
into dvr.py's router via include_router, so it inherits that router's
prefix/auth dependency.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import shlex
import shutil
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from app import config, hls_streaming, media_probe, transcoding
from app.api._hdhomerun_settings import get_hdhomerun_settings
from app.async_utils import drain_stderr_tail, run_in_background, terminate_process
from app.dvr import edl_parser
from app.dvr.builtin.capture import ActiveCapture, capture_pipeline
from app.dvr.builtin.tail_follow import pump_tail_follow
from app.dvr.media import captions_live, captions_static, thumbnails
from app.integrations import hdhomerun_client
from app.storage import db
from app.subprocess_streaming import (
    DETAIL_REASON_CHARS,
    FFMPEG_NOT_FOUND_DETAIL,
    FFMPEG_STARTUP_TIMEOUT_SECONDS,
    STDERR_FLUSH_TIMEOUT_SECONDS,
    STDERR_TAIL_BYTES,
    STREAM_CHUNK_BYTES,
    build_ffmpeg_failure_detail,
    describe_ffmpeg_startup_failure,
    get_recent_stream_failure,
    record_stream_failure,
)

logger = logging.getLogger(__name__)

router = APIRouter()

_FFMPEG_TERMINATE_TIMEOUT_SECONDS = 5

# A capture is registered (and get_active_capture starts returning it) the
# instant its writer ffmpeg process is spawned - well before that ffmpeg has
# actually locked the tuner and flushed any bytes to disk (see
# CapturePipeline.start_capture). Without this pre-flight wait, a viewer
# request landing right after a capture starts would hand the downstream
# transcode ffmpeg an empty pipe and race the writer's own tuner-lock latency
# against _FFMPEG_STARTUP_TIMEOUT_SECONDS, a budget calibrated for a single
# ffmpeg's startup, not two chained ones.
_LIVE_CAPTURE_READY_MIN_BYTES = 32 * 1024
_LIVE_CAPTURE_READY_TIMEOUT_SECONDS = 20
_LIVE_CAPTURE_READY_POLL_SECONDS = 0.2


# ffprobe metadata cache
_PROBE_CACHE_MAX_ENTRIES = 500
_probe_cache: OrderedDict[str, dict[str, Any]] = OrderedDict()

# Separate sticky-on-success cache for in-progress recordings, keyed the same
# way but never sharing entries with _probe_cache: an in-progress probe
# result has no duration_seconds, so once a recording completes it must be
# probed again (fresh entry in _probe_cache) rather than reusing this one.
_probe_cache_in_progress: OrderedDict[str, dict[str, Any]] = OrderedDict()


def _probe_cache_set(recording_id: str, result: dict[str, Any]) -> None:
    _probe_cache[recording_id] = result
    _probe_cache.move_to_end(recording_id)
    while len(_probe_cache) > _PROBE_CACHE_MAX_ENTRIES:
        _probe_cache.popitem(last=False)


def _probe_cache_in_progress_set(recording_id: str, result: dict[str, Any]) -> None:
    _probe_cache_in_progress[recording_id] = result
    _probe_cache_in_progress.move_to_end(recording_id)
    while len(_probe_cache_in_progress) > _PROBE_CACHE_MAX_ENTRIES:
        _probe_cache_in_progress.popitem(last=False)


# comskip/EDL commercial-cutlist cache, keyed by recording_id. Unlike
# _probe_cache, this is invalidated by the sidecar .edl file's mtime rather
# than cached for the process lifetime: comskip runs asynchronously and can
# finish well after a recording is first probed, so a finished recording's
# entry must still notice a newly-written or updated .edl file.
_EDL_CACHE_MAX_ENTRIES = 500
_edl_cache: OrderedDict[str, tuple[float, list[dict[str, float]]]] = OrderedDict()


def invalidate_recording_cache(recording_id: str) -> None:
    """Drop recording_id's cached probe/EDL results, if any. Called on delete
    today; also the hook a future re-encode/replace flow would call before
    regenerating a recording's media file at the same path."""
    _probe_cache.pop(recording_id, None)
    _probe_cache_in_progress.pop(recording_id, None)
    _edl_cache.pop(recording_id, None)


def _load_commercial_segments(recording_id: str, target_url: str) -> list[dict[str, float]]:
    """Load comskip/EDL commercial segments for a finished recording.

    The .edl sidecar lives alongside the recording's media file on disk (the
    third-party comskip tooling convention), so this only applies when
    target_url resolved to a local file path - remote (official HDHomeRun
    DVR) recordings have no sidecar we can read.
    """
    p = Path(target_url)
    if not p.is_file():
        return []

    edl_path = p.with_suffix(".edl")
    try:
        mtime = edl_path.stat().st_mtime
    except OSError:
        _edl_cache.pop(recording_id, None)
        return []

    cached = _edl_cache.get(recording_id)
    if cached is not None and cached[0] == mtime:
        _edl_cache.move_to_end(recording_id)
        return cached[1]

    segments = edl_parser.parse_edl_file(edl_path)
    _edl_cache[recording_id] = (mtime, segments)
    _edl_cache.move_to_end(recording_id)
    while len(_edl_cache) > _EDL_CACHE_MAX_ENTRIES:
        _edl_cache.popitem(last=False)
    return segments


def _resolve_target_media_url(
    settings: dict[str, Any],
    url: str,
    recording_id: str | None = None,
    provider: str | None = None,
) -> str:
    """Resolve a recording URL to either a local file path on disk or a remote HTTP URL.

    `provider` ("builtin" or "hdhomerun"), when the client supplies it, is
    trusted over the heuristics below - it comes from the same
    list_recordings() response that tagged the recording as builtin or
    official in the first place, so it authoritatively answers "does this
    recording belong to our own DVR" without having to infer it from whether
    an official DVR happens to also be configured.
    """
    if url:
        # A local path is only ever trusted if it resolves inside
        # RECORDINGS_DIR - client-supplied `url` otherwise reaches ffmpeg,
        # ffprobe, and FileResponse below, so an unconstrained path here is
        # an arbitrary local file read (e.g. `url=backend/secret.key`).
        # Legitimate local playback URLs always come from list_recordings(),
        # which only ever hands out paths already confined to
        # RECORDINGS_DIR; a remote HDHomeRun-DVR URL never matches this
        # branch since Path(url).exists() is false for an http(s):// value.
        p = Path(url).resolve()
        try:
            p.relative_to(config.RECORDINGS_DIR.resolve())
        except ValueError:
            p = None
        if p is not None and p.exists() and p.is_file():
            return str(p)

    if recording_id:
        rec = db.get_recording(recording_id)
        if rec:
            file_path = rec.get("file_path")
            if file_path:
                p = Path(file_path)
                if p.exists() or capture_pipeline.is_capture_active(recording_id):
                    # An active capture's file may not exist yet - the writer
                    # ffmpeg is registered before it locks the tuner and flushes
                    # its first bytes (see CapturePipeline.start_capture). That's
                    # expected for live TV and just-started recordings; callers
                    # already handle readiness via _wait_for_live_capture_data.
                    return str(p)
            # This recording_id names a builtin-DVR recording (found in our
            # own database), not a remote-engine one - whether its file_path
            # is unset or points at a file no longer on disk, falling through
            # to hdhomerun_client.resolve_recording_url below would treat
            # that local path/ID as a tuner/DVR-relative URL fragment and
            # concatenate it onto http://{dvr_host}:{dvr_port}/, producing a
            # nonsensical URL that ffmpeg then fails to open with an opaque
            # 404. Raise a clear, specific error instead.
            raise HTTPException(
                status_code=404,
                detail=f"Recording file no longer exists on disk: {file_path or '(no file recorded)'}",
            )

        # No local builtin-DVR row for this ID. If the client told us this is
        # a builtin recording, that's authoritative - never fall through to
        # the official DVR, no matter whether one happens to be configured;
        # doing so previously routed builtin recordings the client couldn't
        # find locally (e.g. a stale/cached id) to the HDHomeRun DVR server
        # and produced an opaque 404 from *that* server instead of a clear
        # local one. Without a provider hint (older clients), fall back to
        # the old heuristic: list_recordings() only ever hands a client an
        # official-HDHomeRun-DVR recording_id when
        # hdhomerun_client.is_dvr_configured() is true, so if it's false here
        # this recording_id can't legitimately be one either.
        if provider == "builtin" or (provider is None and not hdhomerun_client.is_dvr_configured(settings)):
            raise HTTPException(
                status_code=404,
                detail=f"Recording not found: {recording_id}",
            )

    try:
        return hdhomerun_client.resolve_recording_url(settings, url)
    except hdhomerun_client.HDHomeRunError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


_TS_PACKET_SIZE = 188


def _estimate_byte_offset(capture: Any, target_start_seconds: float) -> int | None:
    """Coarse elapsed-time-to-bytes-written approximation for seeking into a
    still-growing capture file. GOP-scale accuracy, not exact - the same
    tolerance a live channel change already has. The result is aligned down
    to a whole MPEG-TS packet boundary: an unaligned byte offset lands
    mid-packet and desyncs every subsequent "packet" the downstream ffmpeg
    reads from the tail-follow pipe (PES packet size mismatch / corrupt
    packet errors), unlike a plain live tail-follow, which always starts at
    a whole multiple of the packet size because the writer only ever
    appends whole packets."""
    try:
        file_size = capture.file_path.stat().st_size
    except OSError:
        return None
    elapsed = time.time() - capture.start_ts
    if elapsed <= 0 or file_size <= 0:
        return None
    bytes_per_second = file_size / elapsed
    raw_offset = max(0, int(target_start_seconds * bytes_per_second))
    return (raw_offset // _TS_PACKET_SIZE) * _TS_PACKET_SIZE


async def _wait_for_live_capture_data(capture: ActiveCapture, recording_id: str) -> bool:
    """Block (briefly) until a just-started capture's writer ffmpeg has
    actually flushed some bytes to disk, so the downstream transcode ffmpeg
    we're about to spawn gets real input right away instead of an empty pipe.
    Returns False if the capture disappears (writer failed), its ffmpeg
    process has already exited, or the wait times out with the file still
    effectively empty - callers should treat any of these as a startup
    failure. A no-op for a capture that's already been running for a while,
    since it'll already be well past the byte threshold."""
    deadline = time.monotonic() + _LIVE_CAPTURE_READY_TIMEOUT_SECONDS
    while True:
        try:
            if capture.file_path.stat().st_size >= _LIVE_CAPTURE_READY_MIN_BYTES:
                return True
        except OSError:
            pass
        if not capture_pipeline.is_capture_active(recording_id):
            return False
        # The writer ffmpeg exiting on its own (bad channel, tuner refused
        # the connection, etc.) doesn't remove it from
        # capture_pipeline - only an explicit stop_capture() does - so
        # without this check a dead writer would still burn the full
        # timeout above instead of failing immediately.
        if capture.process is not None and capture.process.returncode is not None:
            return False
        if time.monotonic() >= deadline:
            return False
        await asyncio.sleep(_LIVE_CAPTURE_READY_POLL_SECONDS)


async def _describe_live_capture_failure(capture: ActiveCapture) -> tuple[str, str]:
    """Why the writer ffmpeg never produced data: a one-line cause plus its
    stderr tail, in the same (cause, reason) shape
    describe_ffmpeg_startup_failure returns for the downstream transcode
    ffmpeg - reused here since it's the same "process died or never wrote
    anything, here's its stderr" question, just against the writer instead."""
    if capture.process is None:
        return "capture has no writer process", ""
    return await describe_ffmpeg_startup_failure(
        capture.process,
        capture.stderr_tail,
        capture.stderr_drain_done,
        startup_timeout=_LIVE_CAPTURE_READY_TIMEOUT_SECONDS,
        flush_timeout=STDERR_FLUSH_TIMEOUT_SECONDS,
    )


@router.get("/recording-stream")
async def stream_recording(
    request: Request,
    url: str,
    start: float | None = None,
    audio_index: int | None = None,
    recording_id: str | None = None,
    provider: str | None = None,
):
    cache_key = str(request.url)
    cached_failure = get_recent_stream_failure(cache_key)
    if cached_failure is not None:
        status_code, detail = cached_failure
        raise HTTPException(status_code=status_code, detail=detail)

    settings = await get_hdhomerun_settings()
    # If recording_id names a capture that's still actively being written
    # (live TV, or a recording that's still in progress), tail-follow the
    # growing file instead of reading it as a static, already-complete one -
    # this is what lets a viewer tune into a channel that's already recording
    # instead of waiting for the recording to finish.
    active_capture = await capture_pipeline.get_active_capture(recording_id) if recording_id else None
    target_url = await asyncio.to_thread(_resolve_target_media_url, settings, url, recording_id, provider)

    mode = settings.get("playback_mode", "server_transcode")
    if mode == "server_transcode" or audio_index is not None or start is not None:
        if active_capture is not None and not await _wait_for_live_capture_data(active_capture, recording_id):
            cause, reason = await _describe_live_capture_failure(active_capture)
            logger.error(
                "Recording transcode aborted for %s: capture produced no data within %ss (%s)\n"
                "tuner ffmpeg output:\n%s",
                target_url,
                _LIVE_CAPTURE_READY_TIMEOUT_SECONDS,
                cause,
                reason or "(none)",
            )
            detail = (
                "Could not start streaming recording: tuner did not produce any data within "
                f"{_LIVE_CAPTURE_READY_TIMEOUT_SECONDS}s"
            )
            if reason:
                detail += f". ffmpeg said: {reason[-DETAIL_REASON_CHARS:]}"
            record_stream_failure(cache_key, 502, detail)
            raise HTTPException(status_code=502, detail=detail)
        input_url = "pipe:0" if active_capture is not None else target_url
        # Demuxer-side -ss can't seek a pipe; a seek into a live capture is
        # instead handled by starting the tail-follow pump at an estimated
        # byte offset (below).
        seek_seconds = None if active_capture is not None else start
        try:
            ffmpeg_args = transcoding.build_ffmpeg_args(
                settings, input_url, seek_seconds=seek_seconds, audio_index=audio_index
            )
        except transcoding.InvalidCustomFfmpegArgsError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        preset_id = settings.get("hwaccel", transcoding.DEFAULT_PRESET)
        device = transcoding.resolve_device(settings)
        command = shlex.join(["ffmpeg", *ffmpeg_args])

        try:
            process = await asyncio.create_subprocess_exec(
                "ffmpeg",
                *ffmpeg_args,
                stdin=asyncio.subprocess.PIPE if active_capture is not None else asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as exc:
            record_stream_failure(cache_key, 503, FFMPEG_NOT_FOUND_DETAIL)
            raise HTTPException(status_code=503, detail=FFMPEG_NOT_FOUND_DETAIL) from exc

        assert process.stdout is not None
        assert process.stderr is not None

        logger.info(
            "Starting recording transcode for %s (preset=%s, device=%s, tail_follow=%s): %s",
            target_url,
            preset_id,
            device,
            active_capture is not None,
            command,
        )

        pump_stop_event = asyncio.Event()
        pump_task: asyncio.Task[None] | None = None
        if active_capture is not None:
            assert process.stdin is not None
            start_offset_bytes = _estimate_byte_offset(active_capture, start) if start is not None else None
            pump_task = asyncio.create_task(
                pump_tail_follow(
                    active_capture.file_path,
                    process.stdin,
                    pump_stop_event,
                    lambda: capture_pipeline.is_capture_active(recording_id),
                    start_offset_bytes=start_offset_bytes,
                )
            )

        async def stop_pump() -> None:
            pump_stop_event.set()
            if pump_task is not None:
                with contextlib.suppress(Exception):
                    await pump_task
            if process.stdin is not None:
                with contextlib.suppress(Exception):
                    process.stdin.close()

        stderr_tail = bytearray()
        drain_done = asyncio.Event()
        run_in_background(drain_stderr_tail(process.stderr, stderr_tail, drain_done, tail_bytes=STDERR_TAIL_BYTES))

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
            run_in_background(stop_pump())
            logger.error(
                "Recording transcode failed for %s: %s\nffmpeg output:\n%s", target_url, cause, reason or "(none)"
            )
            detail = await build_ffmpeg_failure_detail(
                "streaming recording", cause, reason, reason_chars=DETAIL_REASON_CHARS
            )
            record_stream_failure(cache_key, 502, detail)
            raise HTTPException(status_code=502, detail=detail)

        async def transcode_generator():
            try:
                yield first_chunk
                while True:
                    chunk = await process.stdout.read(STREAM_CHUNK_BYTES)
                    if not chunk:
                        break
                    yield chunk
            finally:
                run_in_background(terminate_process(process, timeout=_FFMPEG_TERMINATE_TIMEOUT_SECONDS))
                run_in_background(stop_pump())

        return StreamingResponse(
            transcode_generator(),
            media_type="video/mp2t",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
        )

    # Local file direct serving
    p = Path(target_url)
    if p.exists() and p.is_file():
        return FileResponse(p, media_type="video/mp2t")

    # Fallback: proxy the raw remote stream through unmodified.
    async def stream_generator():
        try:
            async with httpx.AsyncClient(timeout=30) as client, client.stream("GET", target_url) as resp:
                if resp.status_code >= 400:
                    yield b""
                    return
                async for chunk in resp.aiter_bytes(chunk_size=65536):
                    yield chunk
        except Exception as exc:
            logger.debug("Recording stream proxy error from %s: %s", target_url, exc)
            yield b""

    return StreamingResponse(stream_generator(), media_type="video/mp2t")


class RecordingStreamHLSRequest(BaseModel):
    url: str
    recording_id: str | None = None
    start: float | None = None
    audio_index: int | None = None
    provider: str | None = None
    for_cast: bool = False


@router.post("/recording-stream-hls")
async def stream_recording_hls(body: RecordingStreamHLSRequest, request: Request):
    """HLS entry point for native (Apple) clients and Google Cast senders -
    the primary playback path (see PlayerViewModel.playChannel). Unlike
    /recording-stream, this always transcodes: AVFoundation (iOS/tvOS's only
    player) can't decode raw MPEG-2, so the direct-file/remote-proxy fallback
    branches that /recording-stream uses for playback_mode != "server_transcode"
    don't apply here regardless of the user's saved playback_mode setting.

    `for_cast=True` (set by a Google Cast sender, web or Android, instead of
    a native Apple client) scopes the returned `playlist_url` to a
    per-session cast token instead of this app's normal cookie/bearer auth -
    see the matching comment on `api/streaming.py`'s `stream_channel_hls`.
    """
    settings = await get_hdhomerun_settings()
    active_capture = (
        await capture_pipeline.get_active_capture(body.recording_id) if body.recording_id else None
    )
    target_url = await asyncio.to_thread(
        _resolve_target_media_url, settings, body.url, body.recording_id, body.provider
    )

    if active_capture is not None and not await _wait_for_live_capture_data(active_capture, body.recording_id):
        cause, reason = await _describe_live_capture_failure(active_capture)
        logger.error(
            "Recording HLS transcode aborted for %s: capture produced no data within %ss (%s)\n"
            "tuner ffmpeg output:\n%s",
            target_url,
            _LIVE_CAPTURE_READY_TIMEOUT_SECONDS,
            cause,
            reason or "(none)",
        )
        detail = (
            "Could not start streaming recording: tuner did not produce any data within "
            f"{_LIVE_CAPTURE_READY_TIMEOUT_SECONDS}s"
        )
        if reason:
            detail += f". ffmpeg said: {reason[-DETAIL_REASON_CHARS:]}"
        raise HTTPException(status_code=502, detail=detail)

    input_url = "pipe:0" if active_capture is not None else target_url
    # Demuxer-side -ss can't seek a pipe; a seek into a live capture is
    # instead handled by starting the tail-follow pump at an estimated byte
    # offset (below) - same split as /recording-stream.
    seek_seconds = None if active_capture is not None else body.start

    session_id, tmp_dir = hls_streaming.allocate_session_dir()
    cast_token = hls_streaming.new_cast_token() if body.for_cast else None
    try:
        ffmpeg_args = transcoding.build_ffmpeg_args(
            settings,
            input_url,
            seek_seconds=seek_seconds,
            audio_index=body.audio_index,
            output_format="hls",
            hls_playlist_path=hls_streaming.playlist_path(tmp_dir),
            hls_segment_pattern=hls_streaming.segment_pattern(tmp_dir),
            hls_vod=active_capture is None,
            hls_keep_segments=active_capture is not None,
            hls_base_url=hls_streaming.cast_base_url(session_id, cast_token) if cast_token else None,
        )
    except transcoding.InvalidCustomFfmpegArgsError as exc:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Started from create_session's on_process_spawned callback (below) so the
    # tail-follow pump is already feeding ffmpeg's stdin *before* create_session
    # starts waiting for a playlist to appear - otherwise ffmpeg sits reading
    # from an open-but-unfed pipe and can never produce output within the
    # startup timeout (see on_process_spawned's docstring in hls_streaming.py).
    pump_task: asyncio.Task[None] | None = None
    pump_stop_event: asyncio.Event | None = None

    def _start_pump(process: asyncio.subprocess.Process) -> None:
        nonlocal pump_task, pump_stop_event
        if active_capture is None:
            return
        assert process.stdin is not None
        start_offset_bytes = _estimate_byte_offset(active_capture, body.start) if body.start is not None else None
        pump_stop_event = asyncio.Event()
        pump_task = asyncio.create_task(
            pump_tail_follow(
                active_capture.file_path,
                process.stdin,
                pump_stop_event,
                lambda: capture_pipeline.is_capture_active(body.recording_id),
                start_offset_bytes=start_offset_bytes,
            )
        )

    try:
        session = await hls_streaming.create_session(
            session_id,
            tmp_dir,
            ffmpeg_args,
            label=f"recording {body.recording_id or target_url}",
            stdin_pipe=active_capture is not None,
            on_process_spawned=_start_pump,
            min_segments=1 if active_capture is None else hls_streaming.HLS_READY_MIN_SEGMENTS,
            cast_token=cast_token,
        )
    except hls_streaming.HLSStartupError as exc:
        if pump_stop_event is not None:
            pump_stop_event.set()
        if pump_task is not None:
            with contextlib.suppress(Exception):
                await pump_task
        raise HTTPException(status_code=502, detail=exc.detail) from exc

    if active_capture is not None:
        assert pump_task is not None and pump_stop_event is not None
        await hls_streaming.attach_pump(session_id, pump_task, pump_stop_event)

    return {
        "session_id": session.session_id,
        "playlist_url": (
            hls_streaming.cast_playlist_url_for_request(str(request.base_url), session.session_id, cast_token)
            if cast_token
            else f"/api/hls/{session.session_id}/playlist.m3u8"
        ),
    }


def _resolve_transcode_info(settings: dict[str, Any]) -> dict[str, Any]:
    """Surfaces what /recording-stream will actually do for playback info's
    benefit - whether the server transcodes at all, and if so, via which
    preset (computed fresh per-request since it reflects current settings,
    not something worth caching).

    Preset/hardware are resolved regardless of `transcoding_enabled`: native
    clients play recordings via /recording-stream-hls, which always
    transcodes (AVFoundation/ExoPlayer's HLS path can't consume raw
    MPEG-2/MPEG-TS) irrespective of this `playback_mode` setting, so they
    need accurate preset info even when it's "external"."""
    transcoding_enabled = settings.get("playback_mode", "server_transcode") == "server_transcode"
    hwaccel = settings.get("hwaccel", transcoding.DEFAULT_PRESET)
    preset = transcoding.resolve_preset(hwaccel)
    return {
        "transcoding": transcoding_enabled,
        "preset": hwaccel,
        "preset_label": preset.label,
        "hardware": preset.hardware,
    }


@router.get("/recording-detail")
async def recording_detail(
    url: str,
    recording_id: str,
    start: float | None = None,
    record_end: float | None = None,
    provider: str | None = None,
):
    settings = await get_hdhomerun_settings()
    transcode_info = _resolve_transcode_info(settings)

    if record_end is None or record_end > time.time():
        if recording_id not in _probe_cache_in_progress:
            target_url = await asyncio.to_thread(
                _resolve_target_media_url, settings, url, recording_id, provider
            )
            result = await media_probe.probe_in_progress(target_url)
            if result is not None:
                _probe_cache_in_progress_set(recording_id, result)
        cached = dict(
            _probe_cache_in_progress.get(recording_id, {"video": None, "audio": [], "has_captions": False})
        )
        # The ffprobe-based has_captions guess above is a one-shot check
        # cached for the life of the recording, and only looks at the first
        # 30s of the file - it can easily fire before the live-caption
        # extraction pipeline has decoded far enough to produce any cues,
        # permanently caching a false negative. Override it with the real
        # signal (has our own pipeline actually written a cue?) whenever
        # that's more current.
        if not cached.get("has_captions"):
            live_vtt = captions_live.live_captions_path(recording_id)
            if live_vtt.exists() and live_vtt.stat().st_size > len("WEBVTT\n\n"):
                cached["has_captions"] = True
        return {
            "is_in_progress": True,
            "duration_seconds": max(0.0, time.time() - start) if start is not None else None,
            "transcode": transcode_info,
            # None until a client has actually requested the secondary
            # track (recording-captions.vtt?track=2), since starting its
            # extraction loop just to answer this field would defeat CC-14's
            # on-demand/lazy design.
            "secondary_captions": captions_live.live_caption_track2_status(recording_id),
            # comskip never runs on an in-progress file, so skip the
            # filesystem stat() this poll would otherwise cost every time.
            "commercial_segments": [],
            **cached,
        }

    target_url = await asyncio.to_thread(_resolve_target_media_url, settings, url, recording_id, provider)

    if recording_id not in _probe_cache:
        result = await media_probe.probe(target_url)
        _probe_cache_set(
            recording_id,
            result
            or {
                "duration_seconds": (record_end - start) if start is not None else None,
                "video": None,
                "audio": [],
                "has_captions": False,
            },
        )

    # Known v1 limitation: opening a just-finished recording before comskip
    # completes yields [] for that whole playback session, since finished
    # recordings aren't polled - re-opening later picks up the markers.
    commercial_segments = _load_commercial_segments(recording_id, target_url)

    return {
        "is_in_progress": False,
        "transcode": transcode_info,
        # Finished recordings only decode via ffmpeg (no verified way to
        # select CEA-608 channel 2 in this build - see generate_captions_vtt),
        # so a secondary track is never available for them.
        "secondary_captions": None,
        "commercial_segments": commercial_segments,
        **_probe_cache[recording_id],
    }


@router.get("/recording-captions.vtt")
async def recording_captions(
    url: str,
    recording_id: str,
    record_end: float | None = None,
    provider: str | None = None,
    track: int = 1,
):
    if track not in (1, 2):
        raise HTTPException(status_code=400, detail="track must be 1 or 2")

    if record_end is None or record_end > time.time():
        active_capture = await capture_pipeline.get_active_capture(recording_id)
        if active_capture is None:
            raise HTTPException(status_code=404, detail="Recording is no longer active")
        captions_live.ensure_live_captions(
            recording_id,
            active_capture.file_path,
            lambda: capture_pipeline.is_capture_active(recording_id),
            capture_start_ts=active_capture.start_ts,
            channel=track,
        )
        live_path = captions_live.live_captions_path(recording_id, channel=track)
        if not live_path.exists():
            # Nothing extracted yet - the client polls again shortly.
            raise HTTPException(status_code=404, detail="No captions extracted yet")
        return FileResponse(live_path, media_type="text/vtt", headers={"Cache-Control": "no-cache"})

    if track == 2:
        # Finished recordings only decode via ffmpeg's movie/subcc filter
        # (generate_captions_vtt), which has no verified way to select
        # CEA-608 channel 2 in this ffmpeg build - explicit 404 rather than
        # silently serving track 1 or pretending to support it.
        raise HTTPException(status_code=404, detail="Secondary caption track not available for finished recordings")

    settings = await get_hdhomerun_settings()
    target_url = await asyncio.to_thread(_resolve_target_media_url, settings, url, recording_id, provider)

    vtt_path = await captions_static.generate_captions_vtt(target_url, recording_id)
    if vtt_path is None:
        raise HTTPException(status_code=404, detail="No closed captions found for this recording")
    return FileResponse(vtt_path, media_type="text/vtt")


def _thumbnails_enabled(settings: dict[str, Any]) -> bool:
    return bool(settings.get("thumbnails_enabled", True))


async def _resolved_duration(target_url: str, recording_id: str) -> float | None:
    if recording_id not in _probe_cache:
        result = await media_probe.probe(target_url)
        if result is not None:
            _probe_cache_set(recording_id, result)
    cached = _probe_cache.get(recording_id)
    if cached and cached.get("duration_seconds"):
        return cached["duration_seconds"]
    return None


async def _resolved_thumbnail_sprite(
    recording_id: str, url: str, record_end: float | None, provider: str | None = None
) -> tuple[Path, Path]:
    settings = await get_hdhomerun_settings()
    if not _thumbnails_enabled(settings):
        raise HTTPException(status_code=404, detail="Thumbnail previews are disabled")
    if record_end is None or record_end > time.time():
        raise HTTPException(status_code=404, detail="Thumbnails are only available for completed recordings")

    target_url = await asyncio.to_thread(_resolve_target_media_url, settings, url, recording_id, provider)
    duration = await _resolved_duration(target_url, recording_id)
    if duration is None:
        raise HTTPException(status_code=404, detail="Could not determine recording duration")

    sprite = await thumbnails.generate_thumbnail_sprite(target_url, recording_id, duration)
    if sprite is None:
        raise HTTPException(status_code=404, detail="Could not generate thumbnail preview")
    return sprite


@router.get("/recording-thumbnails/{recording_id}.jpg")
async def recording_thumbnail_sprite(
    recording_id: str, url: str, record_end: float | None = None, provider: str | None = None
):
    sprite = await _resolved_thumbnail_sprite(recording_id, url, record_end, provider)
    return FileResponse(sprite[0], media_type="image/jpeg")


@router.get("/recording-thumbnails/{recording_id}.vtt")
async def recording_thumbnail_vtt(
    recording_id: str, url: str, record_end: float | None = None, provider: str | None = None
):
    sprite = await _resolved_thumbnail_sprite(recording_id, url, record_end, provider)
    return FileResponse(sprite[1], media_type="text/vtt")
