"""Tiny helper shared by dvr.py and dvr_rules.py (both need HDHomeRun settings
without letting a config/connection failure surface as an HTTP error)."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from app.api._hdhomerun_settings import get_hdhomerun_settings


async def _get_hdhomerun_settings_safe() -> dict[str, Any]:
    try:
        return await get_hdhomerun_settings()
    except HTTPException:
        return {}
