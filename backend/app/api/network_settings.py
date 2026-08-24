"""Connection settings for the household's shared network devices/services:
the HDHomeRun tuner, its optional companion DVR engine, and the two
alternative guide providers (Schedules Direct, XMLTV). One row per type in
the `network_integrations` table (see `app.storage.db`).

Reads are open to any logged-in user; writes require admin.
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.auth import get_current_admin, get_current_user
from app.integrations import hdhomerun_client, schedules_direct
from app.storage.db import (
    NETWORK_INTEGRATION_SECRET_KEYS,
    get_network_integration,
    list_network_integrations,
    save_network_integration,
)

router = APIRouter(prefix="/api/network-settings", tags=["network-settings"], dependencies=[Depends(get_current_user)])

# Display name + starter settings for each known connection type. This app
# only ever has these four fixed connections, so a static table is enough —
# no need for a dynamic plugin-class-by-type lookup.
KNOWN_INTEGRATION_TYPES: dict[str, dict[str, Any]] = {
    "hdhomerun": {
        "name": "HDHomeRun",
        "defaults": {
            "tuner_host": "",
            "tuner_port": 80,
            "dvr_host": "",
            "dvr_port": 59090,
        },
    },
    "schedules_direct": {
        "name": "Schedules Direct",
        "defaults": {
            "username": "",
            "password": "",
        },
    },
    "xmltv": {
        "name": "XMLTV",
        "defaults": {
            "url": "",
        },
    },
    "tmdb": {
        "name": "TMDB",
        "defaults": {
            "api_key": "",
        },
    },
}


def _mask(settings: dict[str, Any]) -> dict[str, Any]:
    # Secrets are write-only in every API response — callers get a boolean
    # "is it set", never the raw value.
    masked: dict[str, Any] = {}
    for key, value in settings.items():
        if key in NETWORK_INTEGRATION_SECRET_KEYS:
            masked[f"has_{key}"] = bool(value)
        else:
            masked[key] = value
    return masked


@router.get("")
async def list_all_network_settings(user: dict[str, Any] = Depends(get_current_user)):
    rows = await asyncio.to_thread(list_network_integrations)
    return [{"id": r["id"], "type": r["type"], "name": r["name"], "settings": _mask(r["settings"])} for r in rows]


@router.get("/{type}")
async def get_network_settings(type: str, user: dict[str, Any] = Depends(get_current_user)):
    info = KNOWN_INTEGRATION_TYPES.get(type)
    if info is None:
        raise HTTPException(status_code=404, detail=f"Unknown network integration type '{type}'")
    row = await asyncio.to_thread(get_network_integration, type)
    if row is None:
        return {"id": type, "type": type, "name": info["name"], "settings": _mask(dict(info["defaults"]))}
    return {"id": row["id"], "type": row["type"], "name": row["name"], "settings": _mask(row["settings"])}


@router.patch("/{type}")
async def update_network_settings(
    type: str, payload: dict[str, Any], admin: dict[str, Any] = Depends(get_current_admin)
):
    info = KNOWN_INTEGRATION_TYPES.get(type)
    if info is None:
        raise HTTPException(status_code=404, detail=f"Unknown network integration type '{type}'")
    existing = await asyncio.to_thread(get_network_integration, type)
    base = existing["settings"] if existing else dict(info["defaults"])
    merged = {**base, **payload}
    await asyncio.to_thread(save_network_integration, type, type, info["name"], merged)
    return {"id": type, "type": type, "name": info["name"], "settings": _mask(merged)}


@router.post("/hdhomerun/test-tuner-connection")
async def test_hdhomerun_tuner_connection(payload: dict[str, Any], admin: dict[str, Any] = Depends(get_current_admin)):
    existing = await asyncio.to_thread(get_network_integration, "hdhomerun")
    candidate = {**(existing["settings"] if existing else {}), **payload}
    try:
        name = await hdhomerun_client.test_tuner_connection(candidate)
    except hdhomerun_client.HDHomeRunError as exc:
        return {"ok": False, "detail": None, "error": str(exc)}
    return {"ok": True, "detail": name, "error": None}


@router.post("/hdhomerun/test-dvr-connection")
async def test_hdhomerun_dvr_connection(payload: dict[str, Any], admin: dict[str, Any] = Depends(get_current_admin)):
    existing = await asyncio.to_thread(get_network_integration, "hdhomerun")
    candidate = {**(existing["settings"] if existing else {}), **payload}
    try:
        name = await hdhomerun_client.test_dvr_connection(candidate)
    except hdhomerun_client.HDHomeRunError as exc:
        return {"ok": False, "detail": None, "error": str(exc)}
    return {"ok": True, "detail": name, "error": None}


async def _get_schedules_direct_token(candidate_payload: dict[str, Any] | None = None) -> str:
    existing = await asyncio.to_thread(get_network_integration, "schedules_direct")
    settings = {**(existing["settings"] if existing else {}), **(candidate_payload or {})}
    username = settings.get("username", "").strip()
    password = settings.get("password", "").strip()
    if not username or not password:
        raise schedules_direct.SchedulesDirectError("Username and password are required")
    auth = await schedules_direct.authenticate(username, password)
    return auth["token"]


@router.post("/schedules-direct/test-connection")
async def test_schedules_direct_connection(
    payload: dict[str, Any], admin: dict[str, Any] = Depends(get_current_admin)
):
    try:
        token = await _get_schedules_direct_token(payload)
        status = await schedules_direct.get_status(token)
        account = status.get("account", {})
        lineups = status.get("lineups", [])
        return {
            "ok": True,
            "detail": {
                "expires": account.get("expires"),
                "max_lineups": account.get("maxLineups"),
                "lineups": lineups,
            },
            "error": None,
        }
    except schedules_direct.SchedulesDirectError as exc:
        return {"ok": False, "detail": None, "error": str(exc)}


@router.get("/schedules-direct/lineups")
async def list_schedules_direct_lineups(admin: dict[str, Any] = Depends(get_current_admin)):
    try:
        token = await _get_schedules_direct_token()
        status = await schedules_direct.get_status(token)
        return status.get("lineups", [])
    except schedules_direct.SchedulesDirectError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/schedules-direct/headends")
async def list_schedules_direct_headends(
    country: str = "USA", postal_code: str = "", admin: dict[str, Any] = Depends(get_current_admin)
):
    if not postal_code:
        raise HTTPException(status_code=400, detail="postal_code parameter is required")
    try:
        token = await _get_schedules_direct_token()
        return await schedules_direct.get_headends(token, country, postal_code)
    except schedules_direct.SchedulesDirectError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/schedules-direct/lineups/{lineup_id}")
async def add_schedules_direct_lineup(lineup_id: str, admin: dict[str, Any] = Depends(get_current_admin)):
    try:
        token = await _get_schedules_direct_token()
        res = await schedules_direct.add_lineup(token, lineup_id)
        return res
    except schedules_direct.SchedulesDirectError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/schedules-direct/lineups/{lineup_id}")
async def delete_schedules_direct_lineup(lineup_id: str, admin: dict[str, Any] = Depends(get_current_admin)):
    try:
        token = await _get_schedules_direct_token()
        res = await schedules_direct.delete_lineup(token, lineup_id)
        return res
    except schedules_direct.SchedulesDirectError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
