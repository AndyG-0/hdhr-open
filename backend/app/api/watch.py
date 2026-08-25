"""Live-watch sessions: auto-starts (or attaches to) a hidden recording behind
every channel a viewer opens (see app.dvr.builtin.watch), so the player can
reuse the existing in-progress-recording playback path to get pause/rewind on
live TV, and so multiple viewers (or a viewer plus a scheduled recording) on
the same channel share a single tuner/capture.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api._hdhomerun_settings import get_hdhomerun_settings
from app.api.dvr import _format_builtin_recording
from app.auth import get_current_user
from app.dvr.builtin import watch
from app.integrations import hdhomerun_client
from app.storage import db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/watch", tags=["watch"], dependencies=[Depends(get_current_user)])


@router.post("/{channel_number}/start")
async def start_watch(channel_number: str):
    settings = await get_hdhomerun_settings()
    if not hdhomerun_client.is_tuner_configured(settings):
        raise HTTPException(status_code=404, detail="Tuner not configured")

    result = await watch.start_watch(channel_number, settings)
    if result is None:
        # No free tuner - caller falls back to plain live streaming.
        return {"recording_id": None, "session_id": None}

    rec = db.get_recording(result["recording_id"])
    body = _format_builtin_recording(rec)
    body["session_id"] = result["session_id"]
    return body


@router.post("/{session_id}/heartbeat", status_code=204)
async def heartbeat_watch(session_id: str):
    ok = await watch.heartbeat_watch(session_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Watch session not found")


@router.post("/{session_id}/stop", status_code=204)
async def stop_watch(session_id: str):
    await watch.stop_watch(session_id)


class PromoteWatchRequest(BaseModel):
    title: str | None = None
    episode_title: str | None = None
    season_number: int | None = None
    episode_number: int | None = None
    synopsis: str | None = None
    image_url: str | None = None
    original_air_date: str | None = None
    category: str | None = None
    end_ts: float | None = None


@router.post("/{session_id}/promote")
async def promote_watch(session_id: str, payload: PromoteWatchRequest):
    settings = await get_hdhomerun_settings()
    recording_id = await watch.promote_watch(
        session_id,
        settings,
        title=payload.title,
        episode_title=payload.episode_title,
        season_number=payload.season_number,
        episode_number=payload.episode_number,
        synopsis=payload.synopsis,
        image_url=payload.image_url,
        original_air_date=payload.original_air_date,
        category=payload.category,
        end_ts=payload.end_ts,
    )
    if recording_id is None:
        raise HTTPException(status_code=404, detail="Watch session not found or already finished")

    rec = db.get_recording(recording_id)
    return _format_builtin_recording(rec)
