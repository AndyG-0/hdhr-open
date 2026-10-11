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
from app.config import resolve_discovery_enabled, resolve_poster_backfill_enabled
from app.dvr.builtin import discovery, poster_lookup

router = APIRouter(prefix="/api/discovery", tags=["discovery"], dependencies=[Depends(get_current_user)])


@router.get("")
async def get_discovery():
    if not resolve_discovery_enabled():
        return {"enabled": False, "has_profile": False, "items": []}
    result = await asyncio.to_thread(discovery.get_discovery_recommendations)
    if resolve_poster_backfill_enabled():
        # Cache-only: discovery items don't carry the channel_id/
        # source_provider/start_ts identity needed to write back into
        # guide_programs, but every resolved poster still lands in the
        # shared poster_url_cache for guide ingestion and recording
        # backfill to reuse, and the response below benefits immediately
        # since `image_url` is mutated in place before we return.
        await poster_lookup.backfill_missing_images(result["items"])
    return {"enabled": True, **result}
