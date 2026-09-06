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
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from app import hls_streaming, media_probe, transcoding
from app.api._hdhomerun_settings import get_hdhomerun_settings
from app.async_utils import drain_stderr_tail, run_in_background, terminate_process
from app.auth import get_current_user
from app.config import RECORDINGS_DIR, resolve_dvr_server_priority
from app.dvr import edl_parser, media_cache
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
    get_recent_stream_failure,
    record_stream_failure,
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


# comskip/EDL commercial-cutlist cache, keyed by recording_id. Unlike
# _probe_cache, this is invalidated by the sidecar .edl file's mtime rather
# than cached for the process lifetime: comskip runs asynchronously and can
# finish well after a recording is first probed, so a finished recording's
# entry must still notice a newly-written or updated .edl file.
_EDL_CACHE_MAX_ENTRIES = 500
_edl_cache: OrderedDict[str, tuple[float, list[dict[str, float]]]] = OrderedDict()


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


async def _get_hdhomerun_settings_safe() -> dict[str, Any]:
    try:
        return await get_hdhomerun_settings()
    except HTTPException:
        return {}


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
        p = Path(url)
        if p.exists() and p.is_file():
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
    if capture_pipeline.is_capture_active(recording_id):
        raise HTTPException(status_code=409, detail="Recording is still in progress")
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
    # Builtin-DVR-only: a caller-supplied title (bypasses guide lookup, so a
    # rule can be created with no backing airing yet), an alternate title
    # match mode, and an inclusion keyword filter checked against episode
    # description/subtitle/category. Not supported by the official
    # HDHomeRun DVR API.
    title: str | None = None
    title_match_mode: str | None = None
    keyword_query: str | None = None


class RecordingRuleUpdateRequest(BaseModel):
    series_id: str | None = None
    date_time: int | None = None
    channel: str | None = None
    recent_only: bool | None = None
    start_padding: int | None = None
    end_padding: int | None = None
    max_episodes_to_keep: int | None = Field(default=None, ge=1)
    server: str | None = None
    title: str | None = None
    title_match_mode: str | None = None
    keyword_query: str | None = None


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
        "TitleMatchMode": rule.get("title_match_mode") or "exact",
        "KeywordQuery": rule.get("keyword_query"),
        "FallbackReason": rule.get("fallback_reason"),
        "fallback_reason": rule.get("fallback_reason"),
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


def _lookup_hdhomerun_series_id(channel: str | None, date_time: int | None, title: str | None) -> str | None:
    """Find a SiliconDust SeriesID from hdhomerun_cloud guide programs."""
    channels = db.list_channels(True)
    all_ch_ids = [c["id"] for c in channels]
    id_by_number = {c["channel_number"]: c["id"] for c in channels if c.get("channel_number")}
    target_ch_id = id_by_number.get(channel) if channel else None

    # 1. Match by channel and airing timestamp
    if date_time:
        ch_list = [target_ch_id] if target_ch_id else all_ch_ids
        programs = db.list_guide_programs(ch_list, date_time - 300, date_time + 300)
        for p in programs:
            if p.get("source_provider") == "hdhomerun_cloud" and p.get("external_program_id"):
                if abs(p["start_ts"] - date_time) <= 120:
                    return p["external_program_id"]

    # 2. Match by channel and title
    if title:
        ch_list = [target_ch_id] if target_ch_id else all_ch_ids
        norm_target = title.strip().lower()
        programs = db.list_guide_programs(ch_list, time.time() - 86400, time.time() + 7 * 86400)
        for p in programs:
            if p.get("source_provider") == "hdhomerun_cloud" and p.get("external_program_id") and p.get("title"):
                norm_p = p["title"].strip().lower()
                if norm_target == norm_p or norm_target in norm_p or norm_p in norm_target:
                    return p["external_program_id"]

    return None


async def _resolve_hdhomerun_series_id(
    series_id: str | None, channel: str | None, date_time: int | None, title: str | None
) -> str | None:
    """Return `series_id` as-is if it's already a real SiliconDust SeriesID,
    otherwise try to resolve one from the hdhomerun_cloud guide."""
    if series_id and series_id != "auto":
        return series_id
    return await asyncio.to_thread(_lookup_hdhomerun_series_id, channel, date_time, title)


async def _create_hdhomerun_recording_rule(
    settings: dict[str, Any],
    *,
    series_id: str | None,
    channel: str | None,
    date_time: int | None,
    recent_only: bool | None,
    start_padding: int | None,
    end_padding: int | None,
) -> None:
    rule_data: dict[str, Any] = {
        "series_id": series_id,
        "channel": channel,
        "date_time": date_time,
        "recent_only": recent_only,
        "start_padding": start_padding,
        "end_padding": end_padding,
    }
    await hdhomerun_client.add_recording_rule(settings, rule_data)


async def _create_builtin_recording_rule(
    *,
    series_id: str | None,
    date_time: int | None,
    channel: str | None,
    recent_only: bool | None,
    start_padding: int | None,
    end_padding: int | None,
    max_episodes_to_keep: int | None,
    title: str | None,
    title_match_mode: str | None,
    keyword_query: str | None,
    fallback_reason: str | None = None,
) -> dict[str, Any]:
    rule_id = f"rule_{uuid.uuid4().hex[:12]}"
    rule_type = "single" if date_time is not None else "series"

    resolved_title = title or await asyncio.to_thread(_lookup_guide_title, series_id, channel, date_time)
    series_match_key = (
        str(date_time)
        if rule_type == "single" and date_time
        else (series_id if series_id and series_id != "auto" else resolved_title)
    )

    rule_entry = {
        "id": rule_id,
        "provider": "builtin",
        "type": rule_type,
        "title": resolved_title or "Untitled",
        "series_match_key": series_match_key,
        "channel_id": channel,
        "start_padding_seconds": start_padding or 0,
        "end_padding_seconds": end_padding or 0,
        "new_only": 1 if recent_only else 0,
        "priority": 0,
        "max_episodes_to_keep": max_episodes_to_keep,
        "title_match_mode": title_match_mode if title_match_mode == "contains" else "exact",
        "keyword_query": keyword_query,
        "fallback_reason": fallback_reason,
    }

    await asyncio.to_thread(db.create_recording_rule, rule_entry)
    run_in_background(expand_rules())
    return rule_entry


@router.post("/recording-rules")
async def create_recording_rule(payload: RecordingRuleCreateRequest, response: Response = None):
    settings = await _get_hdhomerun_settings_safe()
    priority = resolve_dvr_server_priority()
    preferred_server = payload.server if payload.server in ("builtin", "hdhomerun") else None

    # Keyword/contains matching is a builtin-only concept - the official
    # HDHomeRun DVR API has no equivalent, and silently dropping the filter
    # would make the rule over-record.
    is_keyword_rule = bool(payload.keyword_query) or payload.title_match_mode == "contains"
    if is_keyword_rule and preferred_server == "hdhomerun":
        raise HTTPException(
            status_code=400, detail="Keyword/contains-match rules are only supported by the builtin DVR"
        )

    target_servers = [preferred_server] if preferred_server else (["builtin"] if is_keyword_rule else list(priority))

    fallback_reason: str | None = None

    for target_server in target_servers:
        if target_server == "hdhomerun":
            if hdhomerun_client.is_dvr_configured(settings) or hdhomerun_client.is_tuner_configured(settings):
                series_id = await _resolve_hdhomerun_series_id(
                    payload.series_id, payload.channel, payload.date_time, payload.title
                )
                try:
                    await _create_hdhomerun_recording_rule(
                        settings,
                        series_id=series_id,
                        channel=payload.channel,
                        date_time=payload.date_time,
                        recent_only=payload.recent_only,
                        start_padding=payload.start_padding,
                        end_padding=payload.end_padding,
                    )
                    return await list_recording_rules()
                except hdhomerun_client.HDHomeRunError as exc:
                    logger.info("Official DVR rejected rule creation (%s); falling back to Built-in DVR", exc)
                    fallback_reason = "guide_series_id_missing" if ("SeriesID" in str(exc) or not series_id or series_id == "auto") else str(exc)
                    continue
            elif preferred_server == "hdhomerun":
                raise HTTPException(status_code=400, detail="HDHomeRun DVR is not configured")

        elif target_server == "builtin" or fallback_reason is not None:
            await _create_builtin_recording_rule(
                series_id=payload.series_id,
                date_time=payload.date_time,
                channel=payload.channel,
                recent_only=payload.recent_only,
                start_padding=payload.start_padding,
                end_padding=payload.end_padding,
                max_episodes_to_keep=payload.max_episodes_to_keep,
                title=payload.title,
                title_match_mode=payload.title_match_mode,
                keyword_query=payload.keyword_query,
                fallback_reason=fallback_reason,
            )

            if fallback_reason and response is not None:
                response.headers["X-DVR-Fallback"] = "true"
                response.headers["X-DVR-Fallback-Reason"] = fallback_reason

            return await list_recording_rules()

    if fallback_reason is not None:
        await _create_builtin_recording_rule(
            series_id=payload.series_id,
            date_time=payload.date_time,
            channel=payload.channel,
            recent_only=payload.recent_only,
            start_padding=payload.start_padding,
            end_padding=payload.end_padding,
            max_episodes_to_keep=payload.max_episodes_to_keep,
            title=payload.title,
            title_match_mode=payload.title_match_mode,
            keyword_query=payload.keyword_query,
            fallback_reason=fallback_reason,
        )
        if response is not None:
            response.headers["X-DVR-Fallback"] = "true"
            response.headers["X-DVR-Fallback-Reason"] = fallback_reason
        return await list_recording_rules()

    raise HTTPException(status_code=400, detail="No suitable DVR recording engine available")


@router.put("/recording-rules/{rule_id}")
async def update_recording_rule(rule_id: str, payload: RecordingRuleUpdateRequest):
    settings = await _get_hdhomerun_settings_safe()
    set_fields = payload.model_fields_set

    # Check if it's a builtin rule
    rule = await asyncio.to_thread(db.get_recording_rule, rule_id)
    target_provider = payload.server if payload.server in ("builtin", "hdhomerun") else None

    if rule and target_provider == "hdhomerun":
        # Migrate a builtin rule to the official DVR: builtin rows and
        # official-DVR rules live in entirely different places (a local
        # SQLite row vs. a rule owned by the tuner, with its own ID), so
        # "switching providers" means creating an equivalent rule on the
        # target and only removing the original once that succeeds.
        merged_title_match_mode = (
            payload.title_match_mode if "title_match_mode" in set_fields else rule.get("title_match_mode")
        )
        merged_keyword_query = payload.keyword_query if "keyword_query" in set_fields else rule.get("keyword_query")
        is_keyword_rule = bool(merged_keyword_query) or merged_title_match_mode == "contains"
        if is_keyword_rule:
            raise HTTPException(
                status_code=400, detail="Keyword/contains-match rules are only supported by the builtin DVR"
            )

        if not (hdhomerun_client.is_dvr_configured(settings) or hdhomerun_client.is_tuner_configured(settings)):
            raise HTTPException(status_code=400, detail="HDHomeRun DVR is not configured")

        # series_match_key overloads three meanings depending on rule type -
        # see _format_builtin_rule, which decodes it the same way.
        cur_date_time: int | None = None
        cur_series_id: str | None = None
        series_match_key = rule.get("series_match_key")
        if rule.get("type") == "single" and series_match_key:
            with contextlib.suppress(ValueError, TypeError):
                cur_date_time = int(float(series_match_key))
        elif series_match_key and series_match_key != rule.get("title"):
            cur_series_id = series_match_key

        merged_series_id = payload.series_id if "series_id" in set_fields else cur_series_id
        merged_date_time = payload.date_time if "date_time" in set_fields else cur_date_time
        merged_channel = payload.channel if "channel" in set_fields else rule.get("channel_id")
        merged_recent_only = payload.recent_only if "recent_only" in set_fields else bool(rule.get("new_only"))
        merged_start_padding = (
            payload.start_padding if "start_padding" in set_fields else rule.get("start_padding_seconds")
        )
        merged_end_padding = payload.end_padding if "end_padding" in set_fields else rule.get("end_padding_seconds")
        merged_title = payload.title if "title" in set_fields else rule.get("title")

        series_id = await _resolve_hdhomerun_series_id(merged_series_id, merged_channel, merged_date_time, merged_title)
        try:
            await _create_hdhomerun_recording_rule(
                settings,
                series_id=series_id,
                channel=merged_channel,
                date_time=merged_date_time,
                recent_only=merged_recent_only,
                start_padding=merged_start_padding,
                end_padding=merged_end_padding,
            )
        except hdhomerun_client.HDHomeRunError as exc:
            raise HTTPException(status_code=400, detail=f"Could not switch rule to HDHomeRun RECORD: {exc}") from exc

        await asyncio.to_thread(db.delete_recording_rule, rule_id)
        await asyncio.to_thread(db.delete_scheduled_recordings_for_rule, rule_id)
        run_in_background(expand_rules())
        return await list_recording_rules()

    if not rule and target_provider == "builtin":
        # Migrate an official-DVR rule to the builtin engine: create the
        # local row first, then best-effort clean up the tuner-side rule.
        official_rules = await hdhomerun_client.fetch_dvr_recording_rules(settings)
        current = next((r for r in official_rules if r.get("RecordingRuleID") == rule_id), None)
        if current is None:
            raise HTTPException(status_code=404, detail="Recording rule not found")

        merged_series_id = payload.series_id if "series_id" in set_fields else current.get("SeriesID")
        merged_date_time = payload.date_time if "date_time" in set_fields else current.get("DateTimeOnly")
        merged_channel = payload.channel if "channel" in set_fields else current.get("ChannelOnly")
        merged_recent_only = (
            payload.recent_only if "recent_only" in set_fields else bool(current.get("RecentOnly"))
        )
        merged_start_padding = (
            payload.start_padding if "start_padding" in set_fields else current.get("StartPadding")
        )
        merged_end_padding = payload.end_padding if "end_padding" in set_fields else current.get("EndPadding")
        merged_max_episodes_to_keep = (
            payload.max_episodes_to_keep
            if "max_episodes_to_keep" in set_fields
            else current.get("MaxEpisodesToKeep")
        )
        merged_title = payload.title if "title" in set_fields else current.get("Title")

        await _create_builtin_recording_rule(
            series_id=merged_series_id,
            date_time=merged_date_time,
            channel=merged_channel,
            recent_only=merged_recent_only,
            start_padding=merged_start_padding,
            end_padding=merged_end_padding,
            max_episodes_to_keep=merged_max_episodes_to_keep,
            title=merged_title,
            title_match_mode=payload.title_match_mode,
            keyword_query=payload.keyword_query,
        )

        try:
            await hdhomerun_client.delete_recording_rule(settings, rule_id)
        except hdhomerun_client.HDHomeRunError as exc:
            # The new builtin rule already exists and works - a stray
            # duplicate left on the official DVR is a lesser problem than
            # reporting failure after the migration actually succeeded.
            logger.warning("Could not delete official DVR rule %s after migrating it to builtin: %s", rule_id, exc)

        return await list_recording_rules()

    if rule:
        update_fields: dict[str, Any] = {}
        if payload.channel is not None:
            update_fields["channel_id"] = payload.channel or None
        if payload.start_padding is not None:
            update_fields["start_padding_seconds"] = payload.start_padding
        if payload.end_padding is not None:
            update_fields["end_padding_seconds"] = payload.end_padding
        if payload.recent_only is not None:
            update_fields["new_only"] = 1 if payload.recent_only else 0
        if "max_episodes_to_keep" in set_fields:
            update_fields["max_episodes_to_keep"] = payload.max_episodes_to_keep
        if payload.title_match_mode is not None:
            update_fields["title_match_mode"] = payload.title_match_mode if payload.title_match_mode == "contains" else "exact"
        if "keyword_query" in set_fields:
            update_fields["keyword_query"] = payload.keyword_query
        if payload.title is not None:
            update_fields["title"] = payload.title

        if update_fields:
            await asyncio.to_thread(db.update_recording_rule, rule_id, **update_fields)
            await asyncio.to_thread(db.delete_scheduled_recordings_for_rule, rule_id)
            run_in_background(expand_rules())

        return await list_recording_rules()

    # Otherwise forward to official DVR
    try:
        rule_data = payload.model_dump(exclude_unset=True, exclude={"server"})
        await hdhomerun_client.update_recording_rule(settings, rule_id, rule_data)
        return await list_recording_rules()
    except hdhomerun_client.HDHomeRunError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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
            logger.error(
                "Recording transcode aborted for %s: capture produced no data within %ss (tuner likely still locking)",
                target_url,
                _LIVE_CAPTURE_READY_TIMEOUT_SECONDS,
            )
            detail = (
                "Could not start streaming recording: tuner did not produce any data within "
                f"{_LIVE_CAPTURE_READY_TIMEOUT_SECONDS}s"
            )
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
        logger.error(
            "Recording HLS transcode aborted for %s: capture produced no data within %ss (tuner likely still locking)",
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
            live_vtt = media_cache.live_captions_path(recording_id)
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
            "secondary_captions": media_cache.live_caption_track2_status(recording_id),
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
        media_cache.ensure_live_captions(
            recording_id,
            active_capture.file_path,
            lambda: capture_pipeline.is_capture_active(recording_id),
            capture_start_ts=active_capture.start_ts,
            channel=track,
        )
        live_path = media_cache.live_captions_path(recording_id, channel=track)
        if not live_path.exists():
            # Nothing extracted yet - the client polls again shortly.
            raise HTTPException(status_code=404, detail="No captions extracted yet")
        return FileResponse(live_path, media_type="text/vtt")

    if track == 2:
        # Finished recordings only decode via ffmpeg's movie/subcc filter
        # (generate_captions_vtt), which has no verified way to select
        # CEA-608 channel 2 in this ffmpeg build - explicit 404 rather than
        # silently serving track 1 or pretending to support it.
        raise HTTPException(status_code=404, detail="Secondary caption track not available for finished recordings")

    settings = await get_hdhomerun_settings()
    target_url = await asyncio.to_thread(_resolve_target_media_url, settings, url, recording_id, provider)

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

    sprite = await media_cache.generate_thumbnail_sprite(target_url, recording_id, duration)
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
