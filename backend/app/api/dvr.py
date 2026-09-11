"""DVR: recording rules and the recordings library.

Provides a unified DVR interface supporting both the self-hosted ('builtin')
DVR engine and SiliconDust's official HDHomeRun DVR engine (when configured).

Recording rule handling lives in dvr_rules.py and recording playback/metadata
in dvr_streaming.py - both mounted below via include_router so they inherit
this module's prefix and auth dependency.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from app.api._dvr_shared import _get_hdhomerun_settings_safe
from app.async_utils import run_in_background
from app.auth import get_current_user
from app.config import RECORDINGS_DIR, resolve_dvr_server_priority
from app.dvr.builtin import capture, poster_lookup, retention
from app.dvr.builtin.capture import capture_pipeline
from app.dvr.media import thumbnails
from app.integrations import hdhomerun_client
from app.storage import db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/dvr", tags=["dvr"], dependencies=[Depends(get_current_user)])


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
async def list_recordings(
    limit: int | None = Query(default=None, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
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
    if limit is not None:
        # Sliced in Python, post-merge, rather than pushed down as SQL
        # LIMIT/OFFSET on db.list_recordings(): that function has other
        # callers (retention/rule-matching) needing the complete set, and
        # the official-HDHomeRun-DVR fetch above is always unbounded with
        # no pagination API of its own, so a SQL-level limit on just the
        # local source couldn't be combined with it correctly anyway. A
        # self-hosted library is realistically hundreds of rows, so an
        # unbounded fetch + Python slice here has no real cost.
        return results[offset : offset + limit]
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
            poster = await thumbnails.generate_poster(str(p), recording_id)
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
    dvr_streaming.invalidate_recording_cache(recording_id)
    return {"status": "deleted"}


from app.api import dvr_rules, dvr_streaming  # noqa: E402

router.include_router(dvr_rules.router)
router.include_router(dvr_streaming.router)
