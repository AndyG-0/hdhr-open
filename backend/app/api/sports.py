"""Favorite teams/leagues and the broadcast-network-to-channel map that
powers sports auto-recording (see app.dvr.builtin.sports_autorecord).

Reads are open to any logged-in user (team browsing is a harmless read);
mutations are admin-gated per-route, matching app.api.network_settings'
split.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.async_utils import run_in_background
from app.auth import get_current_admin, get_current_user
from app.dvr.builtin.network_affiliates import normalize_major_network_token
from app.dvr.builtin.network_watch_links import known_watch_link
from app.dvr.builtin.sports_autorecord import sync_sports_autorecord
from app.integrations import espn
from app.storage import db

router = APIRouter(prefix="/api/sports", tags=["sports"], dependencies=[Depends(get_current_user)])


class CreateFavoriteRequest(BaseModel):
    league: str
    espn_team_id: str
    team_display_name: str | None = None


class UpdateFavoriteRequest(BaseModel):
    enabled: bool


class SaveNetworkMapRequest(BaseModel):
    channel_id: str


class SaveNetworkWatchLinkRequest(BaseModel):
    url: str


@router.get("/leagues")
async def list_leagues():
    return {"leagues": sorted(espn.LEAGUE_SLUGS)}


@router.get("/leagues/{league}/teams")
async def list_league_teams(league: str):
    teams = await espn.list_league_teams(league)
    if teams is None:
        raise HTTPException(status_code=502, detail="Unable to fetch teams for this league right now")
    return {"teams": teams}


@router.get("/favorites")
async def list_favorites():
    return {"favorites": await asyncio.to_thread(db.list_sports_favorites)}


@router.post("/favorites")
async def create_favorite(payload: CreateFavoriteRequest, admin: dict[str, Any] = Depends(get_current_admin)):
    if payload.league not in espn.LEAGUE_SLUGS:
        raise HTTPException(status_code=422, detail=f"Unknown league {payload.league!r}")
    favorite = {
        "id": f"fav_{uuid.uuid4().hex[:12]}",
        "kind": "team",
        "league": payload.league,
        "espn_team_id": payload.espn_team_id,
        "team_display_name": payload.team_display_name,
        "enabled": True,
        "created_at": datetime.now(UTC).isoformat(),
    }
    await asyncio.to_thread(db.create_sports_favorite, favorite)
    run_in_background(sync_sports_autorecord())
    return favorite


@router.patch("/favorites/{favorite_id}")
async def update_favorite(
    favorite_id: str, payload: UpdateFavoriteRequest, admin: dict[str, Any] = Depends(get_current_admin)
):
    if await asyncio.to_thread(db.get_sports_favorite, favorite_id) is None:
        raise HTTPException(status_code=404, detail="Favorite not found")
    await asyncio.to_thread(db.update_sports_favorite, favorite_id, enabled=int(payload.enabled))
    return await asyncio.to_thread(db.get_sports_favorite, favorite_id)


@router.delete("/favorites/{favorite_id}", status_code=204)
async def delete_favorite(favorite_id: str, admin: dict[str, Any] = Depends(get_current_admin)):
    if await asyncio.to_thread(db.get_sports_favorite, favorite_id) is None:
        raise HTTPException(status_code=404, detail="Favorite not found")

    # Clean up synchronously rather than waiting for the next sync tick, so
    # removing a favorite also removes any recordings it already scheduled.
    for tracked in await asyncio.to_thread(db.list_tracked_events_for_favorite, favorite_id):
        if tracked["recording_rule_id"]:
            await asyncio.to_thread(db.delete_recording_rule, tracked["recording_rule_id"])
            await asyncio.to_thread(db.delete_scheduled_recordings_for_rule, tracked["recording_rule_id"])
        await asyncio.to_thread(db.delete_tracked_event, tracked["espn_event_id"])

    await asyncio.to_thread(db.delete_sports_favorite, favorite_id)


@router.get("/unresolved-networks")
async def list_unresolved_networks():
    unresolved = await asyncio.to_thread(db.list_unresolved_tracked_events)
    by_network: dict[str, dict[str, Any]] = {}
    for event in unresolved:
        network = event["network_name"]
        if network is None:
            continue
        entry = by_network.setdefault(
            network,
            {
                "network_name": network,
                # True means this is a recognized OTA major network (CBS,
                # NBC, ABC, FOX, CW, PBS) that still has no local affiliate
                # match in the channel lineup - distinct from a
                # cable/streaming network (ESPN, TNT, ...), which always
                # requires a manual channel mapping.
                "is_ota": normalize_major_network_token(network) is not None,
                "games": [],
            },
        )
        entry["games"].append(
            {
                "espn_event_id": event["espn_event_id"],
                "league": event["league"],
                "start_ts": event["start_ts"],
                "matchup_title": event.get("matchup_title"),
            }
        )
    for entry in by_network.values():
        entry["games"].sort(key=lambda g: g["start_ts"])
        # A saved custom link (explicit user choice) always wins over the
        # curated default, same precedence as manual-over-auto channel
        # mapping above.
        custom_watch_url = await asyncio.to_thread(db.get_network_watch_link, entry["network_name"])
        entry["custom_watch_url"] = custom_watch_url
        entry["watch_url"] = custom_watch_url or known_watch_link(entry["network_name"])
    return {"unresolved_networks": sorted(by_network.values(), key=lambda e: e["network_name"])}


@router.get("/network-map")
async def list_network_map():
    rows = await asyncio.to_thread(db.list_network_channel_map)
    channels_by_id = {c["id"]: c for c in await asyncio.to_thread(db.list_channels, True)}
    result = []
    for row in rows:
        channel = channels_by_id.get(row["channel_id"])
        result.append(
            {
                "network_name": row["network_name"],
                "channel_id": row["channel_id"],
                "channel_number": channel["channel_number"] if channel else None,
                "channel_name": channel["name"] if channel else None,
                "source": row["source"],
            }
        )
    return {"network_map": result}


@router.put("/network-map/{network_name}")
async def save_network_map_entry(
    network_name: str, payload: SaveNetworkMapRequest, admin: dict[str, Any] = Depends(get_current_admin)
):
    if await asyncio.to_thread(db.get_channel, payload.channel_id) is None:
        raise HTTPException(status_code=422, detail="Unknown channel_id")
    await asyncio.to_thread(db.save_network_channel_map_entry, network_name, payload.channel_id)
    # Take effect immediately rather than waiting up to SYNC_INTERVAL_SECONDS.
    run_in_background(sync_sports_autorecord())
    return {"network_name": network_name, "channel_id": payload.channel_id}


@router.delete("/network-map/{network_name}", status_code=204)
async def delete_network_map_entry(network_name: str, admin: dict[str, Any] = Depends(get_current_admin)):
    await asyncio.to_thread(db.delete_network_channel_map_entry, network_name)


@router.put("/network-watch-link/{network_name}")
async def save_network_watch_link(
    network_name: str, payload: SaveNetworkWatchLinkRequest, admin: dict[str, Any] = Depends(get_current_admin)
):
    url = payload.url.strip()
    if not url or not (url.startswith("http://") or url.startswith("https://")):
        raise HTTPException(status_code=422, detail="url must be a non-empty http(s) URL")
    await asyncio.to_thread(db.save_network_watch_link, network_name, url)
    return {"network_name": network_name, "url": url}


@router.delete("/network-watch-link/{network_name}", status_code=204)
async def delete_network_watch_link(network_name: str, admin: dict[str, Any] = Depends(get_current_admin)):
    await asyncio.to_thread(db.delete_network_watch_link, network_name)
