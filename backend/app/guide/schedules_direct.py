"""Schedules Direct guide persistence.

Runs as a scheduled background job (see register()), pulling EPG data from
Schedules Direct JSON API (20141201) and writing it into guide_programs /
sd_program_cache / sd_station_map so app.api.guide can read purely from the DB.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import UTC, datetime, timedelta
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.integrations import schedules_direct
from app.integrations.schedules_direct import SchedulesDirectError
from app.storage import db

logger = logging.getLogger(__name__)

SOURCE_PROVIDER = "schedules_direct"
REFRESH_INTERVAL_SECONDS = 4 * 3600  # 4 hours
QUERY_DAYS = 14
_JOB_ID = "guide_refresh_schedules_direct"


def register(scheduler: AsyncIOScheduler) -> None:
    scheduler.add_job(
        refresh_schedules_direct_guide,
        "interval",
        seconds=REFRESH_INTERVAL_SECONDS,
        id=_JOB_ID,
        replace_existing=True,
        next_run_time=datetime.now(UTC),
        max_instances=1,
        coalesce=True,
    )


async def _schedules_direct_settings_or_none() -> dict[str, Any] | None:
    row = await asyncio.to_thread(db.get_network_integration, "schedules_direct")
    return row["settings"] if row else None


def _parse_iso_time(dt_str: str | None) -> float | None:
    if not dt_str:
        return None
    try:
        # Handles 2026-08-18T19:00:00Z or similar ISO formats
        clean_str = dt_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(clean_str)
        return dt.timestamp()
    except (ValueError, TypeError):
        return None


def _extract_metadata(program_meta: dict[str, Any]) -> dict[str, Any]:
    """Extract normalized fields from Schedules Direct program object."""
    # Title
    title = ""
    titles = program_meta.get("titles")
    if isinstance(titles, list) and len(titles) > 0 and isinstance(titles[0], dict):
        title = titles[0].get("title120") or titles[0].get("title") or ""
    elif isinstance(program_meta.get("title"), str):
        title = program_meta["title"]

    # Episode title
    episode_title = program_meta.get("episodeTitle150") or program_meta.get("episodeTitle")

    # Season & Episode
    season_number = None
    episode_number = None
    ep_info = program_meta.get("episodeInfo")
    if isinstance(ep_info, dict):
        season_number = ep_info.get("season")
        episode_number = ep_info.get("number")
    elif isinstance(program_meta.get("metadata"), list):
        for m in program_meta["metadata"]:
            if isinstance(m, dict) and "Gracenote" in m:
                gn = m["Gracenote"]
                if isinstance(gn, dict):
                    season_number = gn.get("season")
                    episode_number = gn.get("episode")
                    break

    # Synopsis / Description
    synopsis = None
    desc_obj = program_meta.get("descriptions")
    if isinstance(desc_obj, dict):
        d1000 = desc_obj.get("description1000")
        d100 = desc_obj.get("description100")
        if isinstance(d1000, list) and len(d1000) > 0 and isinstance(d1000[0], dict):
            synopsis = d1000[0].get("description")
        elif isinstance(d100, list) and len(d100) > 0 and isinstance(d100[0], dict):
            synopsis = d100[0].get("description")
    elif isinstance(program_meta.get("description"), str):
        synopsis = program_meta["description"]

    # Original air date
    original_air_date = program_meta.get("originalAirDate")

    # Categories / Genres
    genres = program_meta.get("genres")
    category = ", ".join(genres) if isinstance(genres, list) else None

    # Artwork image
    image_url = None
    if program_meta.get("hasArtwork") or program_meta.get("hasImage"):
        # If resourceID is available
        resource_id = program_meta.get("resourceID")
        if resource_id:
            image_url = f"{schedules_direct.API_BASE_URL}/image/{resource_id}"

    return {
        "title": title,
        "episode_title": episode_title,
        "season_number": season_number,
        "episode_number": episode_number,
        "synopsis": synopsis,
        "original_air_date": original_air_date,
        "category": category,
        "image_url": image_url,
    }


def _auto_map_channels_from_lineup(
    lineup_id: str, lineup_data: dict[str, Any], tuner_channels: list[dict[str, Any]]
) -> None:
    already_mapped = {m["channel_id"] for m in db.list_sd_station_map()}
    channel_map_entries = lineup_data.get("map", [])
    if not isinstance(channel_map_entries, list):
        return

    # Build lookup of stationID by channel number
    station_by_channel_num: dict[str, str] = {}
    for entry in channel_map_entries:
        if isinstance(entry, dict):
            ch_num = str(entry.get("channel", "")).strip()
            station_id = str(entry.get("stationID", "")).strip()
            if ch_num and station_id:
                station_by_channel_num[ch_num] = station_id

    for ch in tuner_channels:
        if ch["id"] in already_mapped:
            continue
        num = ch.get("channel_number", "").strip()
        station_id = station_by_channel_num.get(num)
        if station_id:
            db.upsert_sd_station_map(ch["id"], station_id, lineup_id)
            already_mapped.add(ch["id"])


async def refresh_schedules_direct_guide() -> None:
    """Scheduler job: pull Schedules Direct EPG data and persist it."""
    settings = await _schedules_direct_settings_or_none()
    if not settings:
        return
    username = settings.get("username", "").strip()
    password = settings.get("password", "").strip()
    if not username or not password:
        return

    try:
        auth = await schedules_direct.authenticate(username, password)
    except SchedulesDirectError:
        logger.info("Schedules Direct authentication failed; skipping guide refresh", exc_info=True)
        return

    token = auth["token"]

    # 1. Fetch user lineups and auto-map unmapped channels
    try:
        status_data = await schedules_direct.get_status(token)
    except SchedulesDirectError:
        logger.info("Could not fetch Schedules Direct status; skipping", exc_info=True)
        return

    lineups = status_data.get("lineups", [])
    tuner_channels = await asyncio.to_thread(db.list_channels, True)

    for l_entry in lineups:
        l_id = l_entry.get("lineup")
        if not l_id:
            continue
        try:
            lineup_data = await schedules_direct.get_lineup(token, l_id)
            await asyncio.to_thread(_auto_map_channels_from_lineup, l_id, lineup_data, tuner_channels)
        except SchedulesDirectError:
            logger.warning("Could not fetch lineup details for '%s'", l_id, exc_info=True)

    # 2. Get list of mapped channels
    sd_maps = await asyncio.to_thread(db.list_sd_station_map)
    if not sd_maps:
        logger.info("No channels mapped to Schedules Direct stations; refresh finished")
        return

    station_ids_by_channel: dict[str, str] = {m["channel_id"]: m["station_id"] for m in sd_maps}
    channels_by_station: dict[str, list[str]] = {}
    for ch_id, st_id in station_ids_by_channel.items():
        channels_by_station.setdefault(st_id, []).append(ch_id)

    unique_station_ids = list(channels_by_station.keys())

    # 3. Query schedules for the next QUERY_DAYS days
    # Start querying from yesterday (UTC) to guarantee full coverage
    # for all time zones across the current day and evening hours.
    start_date = datetime.now(UTC).date() - timedelta(days=1)
    dates_to_query = [(start_date + timedelta(days=d)).isoformat() for d in range(QUERY_DAYS + 1)]

    schedule_reqs = [{"stationID": st_id, "date": dates_to_query} for st_id in unique_station_ids]
    try:
        schedules_result = await schedules_direct.get_schedules(token, schedule_reqs)
    except SchedulesDirectError:
        logger.warning("Failed to fetch Schedules Direct schedules", exc_info=True)
        return

    # 4. Gather all needed program IDs and check cache
    needed_program_ids: set[str] = set()
    for station_sched in schedules_result:
        for prog in station_sched.get("programs", []):
            p_id = prog.get("programID")
            if p_id:
                needed_program_ids.add(p_id)

    cached_programs = await asyncio.to_thread(db.get_cached_sd_programs, list(needed_program_ids))
    missing_ids = [p_id for p_id in needed_program_ids if p_id not in cached_programs]

    # 5. Fetch missing program metadata in batches and update cache
    if missing_ids:
        try:
            fetched_meta = await schedules_direct.get_programs(token, missing_ids)
            now_iso = datetime.now(UTC).isoformat()
            cache_entries = [
                {"program_id": m.get("programID"), "metadata": m, "fetched_at": now_iso}
                for m in fetched_meta
                if m.get("programID")
            ]
            await asyncio.to_thread(db.upsert_sd_program_cache, cache_entries)
            # Merge newly fetched into cached_programs
            for entry in cache_entries:
                cached_programs[entry["program_id"]] = entry
        except SchedulesDirectError:
            logger.warning("Failed to fetch program metadata descriptions from Schedules Direct", exc_info=True)

    # 6. Transform schedules into guide_programs rows
    job_start_ts = time.time()
    rows_by_channel: dict[str, list[dict[str, Any]]] = {}

    for station_sched in schedules_result:
        st_id = station_sched.get("stationID")
        channel_ids = channels_by_station.get(st_id, [])
        if not channel_ids:
            continue

        for prog in station_sched.get("programs", []):
            p_id = prog.get("programID")
            air_str = prog.get("airDateTime")
            duration = prog.get("duration", 0)
            start_ts = _parse_iso_time(air_str)
            if start_ts is None:
                continue
            end_ts = start_ts + duration

            meta_entry = cached_programs.get(p_id, {}).get("metadata", {})
            extracted = _extract_metadata(meta_entry)

            is_new = int(bool(prog.get("new") or prog.get("isPremiereOrFinale") == "Season Premiere"))

            for channel_id in channel_ids:
                row = {
                    "channel_id": channel_id,
                    "source_provider": SOURCE_PROVIDER,
                    "external_program_id": p_id,
                    "title": extracted["title"] or "Untitled",
                    "episode_title": extracted["episode_title"],
                    "season_number": extracted["season_number"],
                    "episode_number": extracted["episode_number"],
                    "synopsis": extracted["synopsis"],
                    "start_ts": start_ts,
                    "end_ts": end_ts,
                    "original_air_date": extracted["original_air_date"],
                    "image_url": extracted["image_url"],
                    "is_new": is_new,
                    "category": extracted["category"],
                }
                rows_by_channel.setdefault(channel_id, []).append(row)

    # 7. Write to database
    def _write_db():
        delete_from_ts = job_start_ts - 24 * 3600
        for ch_id, rows in rows_by_channel.items():
            db.delete_future_guide_programs(ch_id, SOURCE_PROVIDER, delete_from_ts)
            db.upsert_guide_programs(rows)
        # Expire cached programs older than 30 days
        expiry_cutoff = (datetime.now(UTC) - timedelta(days=30)).isoformat()
        db.delete_expired_sd_program_cache(expiry_cutoff)
        db.save_guide_provider_state(SOURCE_PROVIDER, datetime.now(UTC).isoformat())

    await asyncio.to_thread(_write_db)
    logger.info(
        "Refreshed Schedules Direct guide (%d channels, %d programs written)",
        len(rows_by_channel),
        sum(len(r) for r in rows_by_channel.values()),
    )
