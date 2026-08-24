"""Shared helper for the tuner/streaming/guide/dvr routers: the household's
one HDHomeRun connection config, edited at `/api/network-settings/hdhomerun`
(see `app.api.network_settings`) rather than per-route.
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import HTTPException

from app.storage.db import get_network_integration


async def get_hdhomerun_settings() -> dict[str, Any]:
    row = await asyncio.to_thread(get_network_integration, "hdhomerun")
    if row is None:
        raise HTTPException(status_code=404, detail="HDHomeRun is not configured")
    return row["settings"]
