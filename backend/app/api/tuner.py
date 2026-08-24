"""The tuner's own lineup and per-tuner-unit status (`/lineup.json`,
`/status.json` on the HDHomeRun device itself) — distinct from guide data
(app.api.guide), which layers program metadata on top of this lineup.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from app.api._hdhomerun_settings import get_hdhomerun_settings
from app.auth import get_current_user
from app.integrations import hdhomerun_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tuner", tags=["tuner"], dependencies=[Depends(get_current_user)])


@router.get("/lineup")
async def get_lineup():
    settings = await get_hdhomerun_settings()
    if not hdhomerun_client.is_tuner_configured(settings):
        raise HTTPException(status_code=404, detail="Tuner not configured")
    return await hdhomerun_client.fetch_lineup(settings)


@router.get("/info")
async def get_tuner_info():
    settings = await get_hdhomerun_settings()
    if not hdhomerun_client.is_tuner_configured(settings):
        raise HTTPException(status_code=404, detail="Tuner not configured")
    discover = await hdhomerun_client.fetch_discover(settings)
    return {
        "friendly_name": discover.get("FriendlyName", "HDHomeRun"),
        "model_number": discover.get("ModelNumber"),
        "firmware_version": discover.get("FirmwareVersion"),
        "tuner_count": discover.get("TunerCount"),
    }


@router.get("/status")
async def get_status():
    settings = await get_hdhomerun_settings()
    if not hdhomerun_client.is_tuner_configured(settings):
        raise HTTPException(status_code=404, detail="Tuner not configured")
    return await hdhomerun_client.fetch_tuner_status(settings)
