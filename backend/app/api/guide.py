"""TV guide data.

Guide *programs* are persisted into `guide_programs` by the background
refresh job in `app.guide.service` and served from the DB here, so the
guide survives a restart and doesn't require a live SiliconDust round-trip
per request. The tuner lineup itself (`GET /api/guide/channels`) is still
fetched live from the tuner — that's a cheap direct hardware call, not what
this persistence work targets.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api._hdhomerun_settings import get_hdhomerun_settings
from app.auth import get_current_admin, get_current_user
from app.config import resolve_guide_provider_priority
from app.guide import schedules_direct as schedules_direct_guide
from app.guide import service, xmltv
from app.guide.service import QUERY_WINDOW_SECONDS
from app.integrations import hdhomerun_client, schedules_direct
from app.storage import db

router = APIRouter(prefix="/api/guide", tags=["guide"], dependencies=[Depends(get_current_user)])


class ChannelSettingsUpdateRequest(BaseModel):
    guide_provider: Literal["hdhomerun_cloud", "xmltv", "schedules_direct"] | None = None
    xmltv_channel_id: str | None = None
    xmltv_display_name: str | None = None
    sd_station_id: str | None = None
    sd_lineup_id: str | None = None
    is_favorite: bool | None = None
    hidden: bool | None = None



def _row_to_airing(row: dict[str, Any], channel_number: str) -> dict[str, Any]:
    episode_number = row["episode_number"]
    if row["season_number"] is not None and episode_number is not None:
        episode_number_str = f"{row['season_number']}.{episode_number}"
    elif episode_number is not None:
        episode_number_str = str(episode_number)
    else:
        episode_number_str = None
    return {
        "series_id": row["external_program_id"],
        "title": row["title"],
        "episode_title": row["episode_title"],
        "episode_number": episode_number_str,
        "synopsis": row["synopsis"],
        "start": row["start_ts"],
        "end": row["end_ts"],
        "original_airdate": row["original_air_date"],
        "image_url": row["image_url"],
        "channel_number": channel_number,
    }


async def _seed_channels_from_tuner_lineup() -> list[dict[str, Any]]:
    """`db.list_channels`, seeding it from the tuner's live lineup first if
    it's empty (e.g. right after initial tuner setup, before the channels
    table has ever been populated).
    """
    channels = await asyncio.to_thread(db.list_channels, True)
    if channels:
        return channels
    try:
        settings = await get_hdhomerun_settings()
        if hdhomerun_client.is_tuner_configured(settings):
            lineup = await hdhomerun_client.fetch_lineup(settings)
            for c in lineup:
                num = c.get("channel_number")
                if num:
                    existing = await asyncio.to_thread(db.get_channel_by_number, num)
                    ch_id = existing["id"] if existing else uuid.uuid4().hex
                    await asyncio.to_thread(db.upsert_channel, ch_id, num, c.get("name") or num, c.get("is_hd", False))
            channels = await asyncio.to_thread(db.list_channels, True)
    except Exception:
        pass
    return channels


@router.get("")
async def get_guide():
    now = time.time()
    channels = await _seed_channels_from_tuner_lineup()

    channels_by_id = {channel["id"]: channel for channel in channels}
    rows = await asyncio.to_thread(
        db.list_guide_programs, list(channels_by_id), now - 6 * 3600, now + QUERY_WINDOW_SECONDS
    )
    priority = resolve_guide_provider_priority()
    resolved = db.resolve_guide_programs(channels, rows, priority)

    result = []
    for channel_id, channel_rows in resolved.items():
        channel = channels_by_id[channel_id]
        result.append(
            {
                "channel_number": channel["channel_number"],
                "channel_name": channel["name"],
                "airings": [_row_to_airing(row, channel["channel_number"]) for row in channel_rows],
            }
        )
    return result


@router.get("/channels")
async def get_channels():
    """The guide-first home's channel list: the tuner's lineup with each
    channel's now/next airing merged in (from the persisted guide) and a
    ready-to-play `playback_url` added, so the client doesn't have to join
    `/api/tuner/lineup` and this route's guide data itself.
    """
    settings = await get_hdhomerun_settings()
    if not hdhomerun_client.is_tuner_configured(settings):
        raise HTTPException(status_code=404, detail="Tuner not configured")

    channels = await hdhomerun_client.fetch_lineup(settings)
    now = time.time()
    db_channels_by_number = {
        channel["channel_number"]: channel for channel in await asyncio.to_thread(db.list_channels, True)
    }
    channel_ids = [channel["id"] for channel in db_channels_by_number.values()]
    rows = await asyncio.to_thread(db.list_guide_programs, channel_ids, now - 6 * 3600, now + 6 * 3600)
    priority = resolve_guide_provider_priority()
    resolved = db.resolve_guide_programs(list(db_channels_by_number.values()), rows, priority)

    guide_available = False
    for p in priority:
        state = await asyncio.to_thread(db.get_guide_provider_state, p)
        if state and state.get("last_refreshed_at"):
            guide_available = True
            break

    for channel in channels:
        channel["playback_url"] = f"/api/streaming/stream/{channel['channel_number']}"
        db_channel = db_channels_by_number.get(channel["channel_number"])
        channel_rows = resolved.get(db_channel["id"], []) if db_channel else []
        current = next_up = None
        for row in channel_rows:
            if row["start_ts"] <= now < row["end_ts"]:
                current = _row_to_airing(row, channel["channel_number"])
            elif row["start_ts"] > now and next_up is None:
                next_up = _row_to_airing(row, channel["channel_number"])
        channel["now"], channel["next"] = current, next_up

    return {"channels": channels, "guide_available": guide_available}


@router.get("/channels/settings")
async def get_channel_settings(user: dict[str, Any] = Depends(get_current_user)):
    channels = await _seed_channels_from_tuner_lineup()

    xmltv_maps = {m["channel_id"]: m for m in await asyncio.to_thread(db.list_xmltv_channel_map)}
    sd_maps = {m["channel_id"]: m for m in await asyncio.to_thread(db.list_sd_station_map)}
    result = []
    for c in channels:
        xm = xmltv_maps.get(c["id"])
        sm = sd_maps.get(c["id"])
        result.append(
            {
                "id": c["id"],
                "channel_number": c["channel_number"],
                "name": c["name"],
                "is_hd": bool(c.get("is_hd", 0)),
                "is_favorite": bool(c.get("is_favorite", 0)),
                "hidden": bool(c.get("hidden", 0)),
                "guide_provider": c.get("guide_provider"),
                "xmltv_channel_id": xm["xmltv_channel_id"] if xm else None,
                "xmltv_display_name": xm["display_name"] if xm else None,
                "sd_station_id": sm["station_id"] if sm else None,
                "sd_lineup_id": sm["lineup_id"] if sm else None,
            }
        )
    return result


@router.patch("/channels/{channel_id}")
async def update_channel_settings(
    channel_id: str, payload: ChannelSettingsUpdateRequest, admin: dict[str, Any] = Depends(get_current_admin)
):
    channel = await asyncio.to_thread(db.get_channel, channel_id)
    if channel is None:
        raise HTTPException(status_code=404, detail=f"Channel '{channel_id}' not found")

    fields_to_update: dict[str, Any] = {}
    if "guide_provider" in payload.model_fields_set:
        fields_to_update["guide_provider"] = payload.guide_provider
    if "is_favorite" in payload.model_fields_set:
        fields_to_update["is_favorite"] = int(bool(payload.is_favorite))
    if "hidden" in payload.model_fields_set:
        fields_to_update["hidden"] = int(bool(payload.hidden))

    if fields_to_update:
        await asyncio.to_thread(db.update_channel, channel_id, **fields_to_update)

    if "xmltv_channel_id" in payload.model_fields_set:
        if payload.xmltv_channel_id and payload.xmltv_channel_id.strip():
            display_name = payload.xmltv_display_name.strip() if payload.xmltv_display_name else None
            await asyncio.to_thread(
                db.upsert_xmltv_channel_map, channel_id, payload.xmltv_channel_id.strip(), display_name
            )
        else:
            await asyncio.to_thread(db.delete_xmltv_channel_map, channel_id)
    elif "xmltv_display_name" in payload.model_fields_set:
        current_map = await asyncio.to_thread(db.get_xmltv_channel_map, channel_id)
        if current_map:
            display_name = payload.xmltv_display_name.strip() if payload.xmltv_display_name else None
            await asyncio.to_thread(
                db.upsert_xmltv_channel_map, channel_id, current_map["xmltv_channel_id"], display_name
            )

    if "sd_station_id" in payload.model_fields_set or "sd_lineup_id" in payload.model_fields_set:
        if payload.sd_station_id and payload.sd_station_id.strip():
            lineup_id = payload.sd_lineup_id.strip() if payload.sd_lineup_id else ""
            await asyncio.to_thread(
                db.upsert_sd_station_map, channel_id, payload.sd_station_id.strip(), lineup_id
            )
        else:
            await asyncio.to_thread(db.delete_sd_station_map, channel_id)

    updated_channel = await asyncio.to_thread(db.get_channel, channel_id)
    xm = await asyncio.to_thread(db.get_xmltv_channel_map, channel_id)
    sm = await asyncio.to_thread(db.get_sd_station_map, channel_id)
    return {
        "id": updated_channel["id"],
        "channel_number": updated_channel["channel_number"],
        "name": updated_channel["name"],
        "is_hd": bool(updated_channel.get("is_hd", 0)),
        "is_favorite": bool(updated_channel.get("is_favorite", 0)),
        "hidden": bool(updated_channel.get("hidden", 0)),
        "guide_provider": updated_channel.get("guide_provider"),
        "xmltv_channel_id": xm["xmltv_channel_id"] if xm else None,
        "xmltv_display_name": xm["display_name"] if xm else None,
        "sd_station_id": sm["station_id"] if sm else None,
        "sd_lineup_id": sm["lineup_id"] if sm else None,
    }


@router.get("/xmltv-feed-channels")
async def get_xmltv_feed_channels(admin: dict[str, Any] = Depends(get_current_admin)):
    row = await asyncio.to_thread(db.get_network_integration, "xmltv")
    url = row["settings"].get("url") if row else None
    if not url:
        return []
    root = await xmltv._fetch_xmltv_root(url)
    if root is None:
        return []
    parsed = xmltv._parse_channels(root)
    return [{"xmltv_channel_id": x_id, "display_names": names} for x_id, names in parsed.items()]


@router.get("/schedules-direct-stations")
async def get_schedules_direct_stations(admin: dict[str, Any] = Depends(get_current_admin)):
    row = await asyncio.to_thread(db.get_network_integration, "schedules_direct")
    if not row or not row["settings"].get("username") or not row["settings"].get("password"):
        return []
    username = row["settings"]["username"]
    password = row["settings"]["password"]
    try:
        auth = await schedules_direct.authenticate(username, password)
        status = await schedules_direct.get_status(auth["token"])
        stations: list[dict[str, Any]] = []
        for l_entry in status.get("lineups", []):
            l_id = l_entry.get("lineup")
            if not l_id:
                continue
            lineup_data = await schedules_direct.get_lineup(auth["token"], l_id)
            station_info = {s["stationID"]: s for s in lineup_data.get("stations", []) if "stationID" in s}
            for m in lineup_data.get("map", []):
                st_id = m.get("stationID")
                if st_id and st_id in station_info:
                    st = station_info[st_id]
                    stations.append(
                        {
                            "station_id": st_id,
                            "lineup_id": l_id,
                            "lineup_name": l_entry.get("name") or l_id,
                            "channel_number": m.get("channel"),
                            "name": st.get("name"),
                            "callsign": st.get("callsign"),
                        }
                    )
        return stations
    except schedules_direct.SchedulesDirectError:
        return []


@router.get("/xmltv/stats")
async def get_xmltv_stats(user: dict[str, Any] = Depends(get_current_user)):
    return await asyncio.to_thread(db.get_xmltv_guide_stats)


@router.post("/xmltv/reload")
async def reload_xmltv(admin: dict[str, Any] = Depends(get_current_admin)):
    try:
        stats = await xmltv.reload_xmltv_guide()
        return {"ok": True, "stats": stats, "message": "XMLTV guide reloaded successfully"}
    except xmltv.XMLTVError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/refresh")
async def refresh_guide(admin: dict[str, Any] = Depends(get_current_admin)):
    asyncio.create_task(service.refresh_hdhomerun_guide())
    asyncio.create_task(xmltv.refresh_xmltv_guide())
    asyncio.create_task(schedules_direct_guide.refresh_schedules_direct_guide())
    return {"status": "ok", "message": "Guide refresh initiated"}

