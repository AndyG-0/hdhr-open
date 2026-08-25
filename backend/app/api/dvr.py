"""DVR: recording rules and the recordings library.

Provides a unified DVR interface supporting both the self-hosted ('builtin') DVR
engine and SiliconDust's official HDHomeRun DVR engine (when configured).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import shlex
import shutil
import time
import uuid
from collections import OrderedDict
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from app import media_probe, transcoding
from app.api._hdhomerun_settings import get_hdhomerun_settings
from app.async_utils import drain_stderr_tail, run_in_background, terminate_process
from app.auth import get_current_user
from app.config import RECORDINGS_DIR, resolve_dvr_server_priority
from app.dvr import media_cache
from app.dvr.builtin import capture, poster_lookup, retention
from app.dvr.builtin.capture import ActiveCapture, capture_pipeline
from app.dvr.builtin.rule_expander import expand_rules
from app.dvr.builtin.tail_follow import pump_tail_follow
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
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/dvr", tags=["dvr"], dependencies=[Depends(get_current_user)])

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


async def _get_hdhomerun_settings_safe() -> dict[str, Any]:
    try:
        return await get_hdhomerun_settings()
    except HTTPException:
        return {}


def _resolve_target_media_url(settings: dict[str, Any], url: str, recording_id: str | None = None) -> str:
    """Resolve a recording URL to either a local file path on disk or a remote HTTP URL."""
    if url:
        p = Path(url)
        if p.exists() and p.is_file():
            return str(p)

    if recording_id:
        rec = db.get_recording(recording_id)
        if rec and rec.get("file_path"):
            p = Path(rec["file_path"])
            if p.exists():
                return str(p)

    return hdhomerun_client.resolve_recording_url(settings, url)


@router.get("/info")
async def get_dvr_info():
    settings = await _get_hdhomerun_settings_safe()
    priority = resolve_dvr_server_priority()
    official_info = None
    if hdhomerun_client.is_dvr_configured(settings):
        try:
            official_info = await hdhomerun_client.fetch_dvr_info(settings)
        except Exception:
            logger.debug("Could not fetch official DVR info", exc_info=True)

    # Builtin DVR info
    free_space = None
    if RECORDINGS_DIR.exists():
        try:
            free_space = shutil.disk_usage(RECORDINGS_DIR).free
        except Exception:
            pass

    builtin_info = {
        "friendly_name": "HDHomeRun Open Built-in DVR",
        "version": "1.0",
        "free_space_bytes": free_space,
        "is_builtin": True,
        "provider": "builtin",
    }

    if priority[0] == "hdhomerun" and official_info is not None:
        return {
            **official_info,
            "is_builtin": False,
            "provider": "hdhomerun",
            "server_priority": list(priority),
            "builtin_storage": builtin_info,
        }

    return {
        **builtin_info,
        "server_priority": list(priority),
        "official_dvr": official_info,
    }


def _format_builtin_recording(r: dict[str, Any]) -> dict[str, Any]:
    season_num = r.get("season_number")
    episode_num = r.get("episode_number")
    if season_num is not None and episode_num is not None:
        ep_str = f"{season_num}.{episode_num}"
    elif episode_num is not None:
        ep_str = str(episode_num)
    else:
        ep_str = None

    start_ts = r.get("start_ts")
    end_ts = r.get("end_ts")
    duration = r.get("duration_seconds")
    if duration is None:
        if start_ts is not None and end_ts is not None:
            duration = end_ts - start_ts
        elif start_ts is not None:
            duration = max(0.0, time.time() - start_ts)

    image_url = r.get("image_url")
    if not image_url and r.get("status") == "completed" and r.get("file_path"):
        image_url = f"/api/dvr/recordings/{r['id']}/poster.jpg"

    return {
        "recording_id": r["id"],
        "series_id": None,
        "title": r.get("title", ""),
        "episode_title": r.get("episode_title"),
        "season_number": season_num,
        "episode_number": ep_str,
        "synopsis": r.get("synopsis"),
        "channel_number": r.get("channel_id"),
        "channel_name": r.get("channel_name_snapshot"),
        "start": start_ts,
        "record_end": end_ts,
        "duration_seconds": duration,
        "file_size_bytes": r.get("file_size_bytes"),
        "play_url": r.get("file_path") or f"/recorded/{r['id']}",
        "image_url": image_url,
        "has_captions": bool(r.get("has_captions")),
        "video_codec": r.get("video_codec"),
        "video_width": r.get("video_width"),
        "video_height": r.get("video_height"),
        "audio_codec": r.get("audio_codec"),
        "audio_channels": r.get("audio_channels"),
        "original_air_date": r.get("original_air_date"),
        "category": r.get("category"),
        "category_type": poster_lookup.classify_category(
            title=r.get("title", ""),
            episode_title=r.get("episode_title"),
            category=r.get("category"),
        ),
        "is_dvr_file": True,
        "status": r.get("status", "completed"),
        "provider": "builtin",
    }


@router.get("/recordings")
async def list_recordings():
    settings = await _get_hdhomerun_settings_safe()
    results: list[dict[str, Any]] = []

    # 1. Builtin DVR recordings from SQLite
    builtin_rows = await asyncio.to_thread(db.list_recordings)
    for row in builtin_rows:
        results.append(_format_builtin_recording(row))
        # Best-effort background poster backfill for existing rows lacking image_url
        if not row.get("image_url"):
            run_in_background(
                capture._backfill_poster(
                    row["id"],
                    row.get("title", ""),
                    row.get("episode_title"),
                    row.get("season_number"),
                    row.get("episode_number"),
                    row.get("category"),
                )
            )

    # 2. Official HDHomeRun DVR recordings (if configured)
    if hdhomerun_client.is_dvr_configured(settings):
        try:
            official_recs = await hdhomerun_client.fetch_dvr_recordings(settings)
            for rec in official_recs:
                rec_copy = dict(rec)
                rec_copy.setdefault("provider", "hdhomerun")
                results.append(rec_copy)
        except Exception:
            logger.debug("Could not fetch official DVR recordings", exc_info=True)

    results.sort(key=lambda r: r.get("start") or 0, reverse=True)
    return results


@router.get("/recordings/{recording_id}/poster.jpg")
async def get_recording_poster(recording_id: str):
    rec = await asyncio.to_thread(db.get_recording, recording_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Recording not found")

    file_path = rec.get("file_path")
    if file_path:
        p = Path(file_path)
        if p.exists() and p.is_file():
            poster = await media_cache.generate_poster(str(p), recording_id)
            if poster and poster.exists():
                return FileResponse(poster, media_type="image/jpeg")

    image_url = rec.get("image_url")
    if image_url:
        from fastapi.responses import RedirectResponse

        return RedirectResponse(image_url)

    raise HTTPException(status_code=404, detail="No poster available for this recording")


@router.delete("/recordings/{recording_id}")
async def delete_recording(recording_id: str):
    deleted = await retention.delete_local_recording(recording_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Recording not found")
    return {"status": "deleted"}


class RecordingRuleCreateRequest(BaseModel):
    series_id: str | None = None
    date_time: int | None = None
    channel: str | None = None
    recent_only: bool | None = None
    start_padding: int | None = None
    end_padding: int | None = None
    max_episodes_to_keep: int | None = Field(default=None, ge=1)
    server: str | None = None


def _format_builtin_rule(rule: dict[str, Any]) -> dict[str, Any]:
    rule_type = rule.get("type", "series")
    series_key = rule.get("series_match_key")
    dt_only = None
    if rule_type == "single" and series_key:
        try:
            dt_only = int(float(series_key))
        except ValueError:
            pass

    return {
        "RecordingRuleID": rule["id"],
        "SeriesID": series_key if series_key and not dt_only else (series_key or "auto"),
        "Title": rule.get("title", ""),
        "DateTimeOnly": dt_only,
        "ChannelOnly": rule.get("channel_id"),
        "RecentOnly": 1 if rule.get("new_only") else 0,
        "StartPadding": rule.get("start_padding_seconds", 0),
        "EndPadding": rule.get("end_padding_seconds", 0),
        "MaxEpisodesToKeep": rule.get("max_episodes_to_keep"),
        "Provider": "builtin",
        "provider": "builtin",
    }


@router.get("/recording-rules")
async def list_recording_rules():
    settings = await _get_hdhomerun_settings_safe()
    results: list[dict[str, Any]] = []

    # 1. Builtin recording rules from SQLite
    builtin_rules = await asyncio.to_thread(db.list_recording_rules, "builtin")
    for rule in builtin_rules:
        results.append(_format_builtin_rule(rule))

    # 2. Official HDHomeRun DVR recording rules (if configured)
    if hdhomerun_client.is_dvr_configured(settings) or hdhomerun_client.is_tuner_configured(settings):
        try:
            official_rules = await hdhomerun_client.fetch_dvr_recording_rules(settings)
            # Exclude duplicate IDs if any
            existing_ids = {r["RecordingRuleID"] for r in results}
            for off in official_rules:
                if off.get("RecordingRuleID") not in existing_ids:
                    off_copy = dict(off)
                    off_copy.setdefault("Provider", "hdhomerun")
                    off_copy.setdefault("provider", "hdhomerun")
                    results.append(off_copy)
        except Exception:
            logger.debug("Could not fetch official DVR recording rules", exc_info=True)

    return results


def _lookup_guide_title(series_id: str | None, channel: str | None, date_time: int | None) -> str:
    """Find a friendly show title in stored guide_programs."""
    channels = db.list_channels(True)
    all_ch_ids = [c["id"] for c in channels]
    id_by_number = {c["channel_number"]: c["id"] for c in channels if c.get("channel_number")}
    target_ch_id = id_by_number.get(channel) if channel else None

    if date_time:
        ch_list = [target_ch_id] if target_ch_id else all_ch_ids
        programs = db.list_guide_programs(ch_list, date_time - 300, date_time + 300)
        for p in programs:
            if abs(p["start_ts"] - date_time) < 300 and p.get("title"):
                return p["title"]

    if series_id and series_id != "auto":
        programs = db.list_guide_programs(all_ch_ids, time.time() - 86400, time.time() + 14 * 86400)
        for p in programs:
            if p.get("external_program_id") == series_id and p.get("title"):
                return p["title"]

    if channel:
        return f"Channel {channel}"
    return series_id or "Untitled Recording"


@router.post("/recording-rules")
async def create_recording_rule(payload: RecordingRuleCreateRequest):
    settings = await _get_hdhomerun_settings_safe()
    priority = resolve_dvr_server_priority()
    preferred_server = payload.server if payload.server in ("builtin", "hdhomerun") else None

    target_servers = [preferred_server] if preferred_server else list(priority)

    for target_server in target_servers:
        if target_server == "hdhomerun":
            if hdhomerun_client.is_dvr_configured(settings) or hdhomerun_client.is_tuner_configured(settings):
                try:
                    rule_data = payload.model_dump(exclude={"server"})
                    await hdhomerun_client.add_recording_rule(settings, rule_data)
                    return await list_recording_rules()
                except hdhomerun_client.HDHomeRunError as exc:
                    logger.info("Official DVR rejected rule creation (%s)", exc)
                    if preferred_server == "hdhomerun":
                        raise HTTPException(status_code=400, detail=str(exc)) from exc
            elif preferred_server == "hdhomerun":
                raise HTTPException(status_code=400, detail="HDHomeRun DVR is not configured")

        elif target_server == "builtin":
            rule_id = f"rule_{uuid.uuid4().hex[:12]}"
            rule_type = "single" if payload.date_time is not None else "series"

            title = await asyncio.to_thread(_lookup_guide_title, payload.series_id, payload.channel, payload.date_time)
            series_match_key = (
                str(payload.date_time)
                if rule_type == "single" and payload.date_time
                else (payload.series_id if payload.series_id != "auto" else title)
            )

            rule_entry = {
                "id": rule_id,
                "provider": "builtin",
                "type": rule_type,
                "title": title,
                "series_match_key": series_match_key,
                "channel_id": payload.channel,
                "start_padding_seconds": payload.start_padding or 0,
                "end_padding_seconds": payload.end_padding or 0,
                "new_only": 1 if payload.recent_only else 0,
                "priority": 0,
                "max_episodes_to_keep": payload.max_episodes_to_keep,
            }

            await asyncio.to_thread(db.create_recording_rule, rule_entry)
            run_in_background(expand_rules())

            return await list_recording_rules()

    raise HTTPException(status_code=400, detail="No suitable DVR recording engine available")


@router.delete("/recording-rules/{rule_id}")
async def delete_recording_rule(rule_id: str):
    settings = await _get_hdhomerun_settings_safe()

    # Check if it's a builtin rule
    rule = await asyncio.to_thread(db.get_recording_rule, rule_id)
    if rule:
        await asyncio.to_thread(db.delete_recording_rule, rule_id)
        await asyncio.to_thread(db.delete_scheduled_recordings_for_rule, rule_id)
        return await list_recording_rules()

    # Otherwise forward to official DVR
    try:
        return await hdhomerun_client.delete_recording_rule(settings, rule_id)
    except hdhomerun_client.HDHomeRunError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _estimate_byte_offset(capture: Any, target_start_seconds: float) -> int | None:
    """Coarse elapsed-time-to-bytes-written approximation for seeking into a
    still-growing capture file. GOP-scale accuracy, not exact - the same
    tolerance a live channel change already has."""
    try:
        file_size = capture.file_path.stat().st_size
    except OSError:
        return None
    elapsed = time.time() - capture.start_ts
    if elapsed <= 0 or file_size <= 0:
        return None
    bytes_per_second = file_size / elapsed
    return max(0, int(target_start_seconds * bytes_per_second))


async def _wait_for_live_capture_data(capture: ActiveCapture, recording_id: str) -> bool:
    """Block (briefly) until a just-started capture's writer ffmpeg has
    actually flushed some bytes to disk, so the downstream transcode ffmpeg
    we're about to spawn gets real input right away instead of an empty pipe.
    Returns False if the capture disappears (writer failed) or the wait times
    out with the file still effectively empty - callers should treat either
    as a startup failure. A no-op for a capture that's already been running
    for a while, since it'll already be well past the byte threshold."""
    deadline = time.monotonic() + _LIVE_CAPTURE_READY_TIMEOUT_SECONDS
    while True:
        try:
            if capture.file_path.stat().st_size >= _LIVE_CAPTURE_READY_MIN_BYTES:
                return True
        except OSError:
            pass
        if not capture_pipeline.is_capture_active(recording_id):
            return False
        if time.monotonic() >= deadline:
            return False
        await asyncio.sleep(_LIVE_CAPTURE_READY_POLL_SECONDS)


@router.get("/recording-stream")
async def stream_recording(
    url: str,
    start: float | None = None,
    audio_index: int | None = None,
    recording_id: str | None = None,
):
    settings = await get_hdhomerun_settings()
    # If recording_id names a capture that's still actively being written
    # (live TV, or a recording that's still in progress), tail-follow the
    # growing file instead of reading it as a static, already-complete one -
    # this is what lets a viewer tune into a channel that's already recording
    # instead of waiting for the recording to finish.
    active_capture = await capture_pipeline.get_active_capture(recording_id) if recording_id else None
    target_url = await asyncio.to_thread(_resolve_target_media_url, settings, url, recording_id)

    mode = settings.get("playback_mode", "server_transcode")
    if mode == "server_transcode":
        if active_capture is not None and not await _wait_for_live_capture_data(active_capture, recording_id):
            logger.error(
                "Recording transcode aborted for %s: capture produced no data within %ss (tuner likely still locking)",
                target_url,
                _LIVE_CAPTURE_READY_TIMEOUT_SECONDS,
            )
            raise HTTPException(
                status_code=502,
                detail=(
                    "Could not start streaming recording: tuner did not produce any data within "
                    f"{_LIVE_CAPTURE_READY_TIMEOUT_SECONDS}s"
                ),
            )
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


def _resolve_transcode_info(settings: dict[str, Any]) -> dict[str, Any]:
    """Surfaces what /recording-stream will actually do for playback info's
    benefit - whether the server transcodes at all, and if so, via which
    preset (computed fresh per-request since it reflects current settings,
    not something worth caching)."""
    transcoding_enabled = settings.get("playback_mode", "server_transcode") == "server_transcode"
    if not transcoding_enabled:
        return {"transcoding": False, "preset": None, "preset_label": None, "hardware": False}
    hwaccel = settings.get("hwaccel", transcoding.DEFAULT_PRESET)
    preset = transcoding.resolve_preset(hwaccel)
    return {"transcoding": True, "preset": hwaccel, "preset_label": preset.label, "hardware": preset.hardware}


@router.get("/recording-detail")
async def recording_detail(url: str, recording_id: str, start: float | None = None, record_end: float | None = None):
    settings = await get_hdhomerun_settings()
    transcode_info = _resolve_transcode_info(settings)

    if record_end is None or record_end > time.time():
        if recording_id not in _probe_cache_in_progress:
            target_url = await asyncio.to_thread(_resolve_target_media_url, settings, url, recording_id)
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
            live_vtt = media_cache.live_captions_path(recording_id)
            if live_vtt.exists() and live_vtt.stat().st_size > len("WEBVTT\n\n"):
                cached["has_captions"] = True
        return {
            "is_in_progress": True,
            "duration_seconds": max(0.0, time.time() - start) if start is not None else None,
            "transcode": transcode_info,
            **cached,
        }

    if recording_id not in _probe_cache:
        target_url = await asyncio.to_thread(_resolve_target_media_url, settings, url, recording_id)
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

    return {"is_in_progress": False, "transcode": transcode_info, **_probe_cache[recording_id]}


@router.get("/recording-captions.vtt")
async def recording_captions(url: str, recording_id: str, record_end: float | None = None):
    if record_end is None or record_end > time.time():
        active_capture = await capture_pipeline.get_active_capture(recording_id)
        if active_capture is None:
            raise HTTPException(status_code=404, detail="Recording is no longer active")
        media_cache.ensure_live_captions(
            recording_id,
            active_capture.file_path,
            lambda: capture_pipeline.is_capture_active(recording_id),
            capture_start_ts=active_capture.start_ts,
        )
        live_path = media_cache.live_captions_path(recording_id)
        if not live_path.exists():
            # Nothing extracted yet - the client polls again shortly.
            raise HTTPException(status_code=404, detail="No captions extracted yet")
        return FileResponse(live_path, media_type="text/vtt")

    settings = await get_hdhomerun_settings()
    target_url = await asyncio.to_thread(_resolve_target_media_url, settings, url, recording_id)

    vtt_path = await media_cache.generate_captions_vtt(target_url, recording_id)
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


async def _resolved_thumbnail_sprite(recording_id: str, url: str, record_end: float | None) -> tuple[Path, Path]:
    settings = await get_hdhomerun_settings()
    if not _thumbnails_enabled(settings):
        raise HTTPException(status_code=404, detail="Thumbnail previews are disabled")
    if record_end is None or record_end > time.time():
        raise HTTPException(status_code=404, detail="Thumbnails are only available for completed recordings")

    target_url = await asyncio.to_thread(_resolve_target_media_url, settings, url, recording_id)
    duration = await _resolved_duration(target_url, recording_id)
    if duration is None:
        raise HTTPException(status_code=404, detail="Could not determine recording duration")

    sprite = await media_cache.generate_thumbnail_sprite(target_url, recording_id, duration)
    if sprite is None:
        raise HTTPException(status_code=404, detail="Could not generate thumbnail preview")
    return sprite


@router.get("/recording-thumbnails/{recording_id}.jpg")
async def recording_thumbnail_sprite(recording_id: str, url: str, record_end: float | None = None):
    sprite = await _resolved_thumbnail_sprite(recording_id, url, record_end)
    return FileResponse(sprite[0], media_type="image/jpeg")


@router.get("/recording-thumbnails/{recording_id}.vtt")
async def recording_thumbnail_vtt(recording_id: str, url: str, record_end: float | None = None):
    sprite = await _resolved_thumbnail_sprite(recording_id, url, record_end)
    return FileResponse(sprite[1], media_type="text/vtt")
