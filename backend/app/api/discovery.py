"""Discovery: locally-scored recommendations for upcoming guide airings.

See app.dvr.builtin.discovery for the scoring/fallback logic. `enabled` is
returned alongside the recommendations (rather than requiring a separate
settings fetch) so any household member - not just admins, who are the only
ones who can read /api/settings - can gate a nav link/tab on it with a
single request.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends

from app.auth import get_current_user
from app.config import resolve_discovery_enabled
from app.dvr.builtin import discovery

router = APIRouter(prefix="/api/discovery", tags=["discovery"], dependencies=[Depends(get_current_user)])


@router.get("")
async def get_discovery():
    if not resolve_discovery_enabled():
        return {"enabled": False, "has_profile": False, "items": []}
    result = await asyncio.to_thread(discovery.get_discovery_recommendations)
    return {"enabled": True, **result}
