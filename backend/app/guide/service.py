"""HDHomeRun cloud guide persistence.

Runs as a scheduled background job (see register()), pulling
hdhomerun_client.fetch_full_guide() and writing it into guide_programs /
channels so app.api.guide can read purely from the DB. XMLTV/Schedules
Direct sources are a separate, not-yet-built follow-up (see ROADMAP.md);
this module only owns the "hdhomerun_cloud" provider.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
import uuid
from datetime import UTC, datetime
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.integrations import hdhomerun_client
from app.integrations.hdhomerun_client import HDHomeRunError
from app.storage import db

logger = logging.getLogger(__name__)

SOURCE_PROVIDER = "hdhomerun_cloud"
REFRESH_INTERVAL_SECONDS = 3600  # matches the previous fetch_full_guide TTL assumption
QUERY_WINDOW_SECONDS = 14 * 24 * 3600  # matches hdhomerun_client._FULL_GUIDE_MAX_DAYS
_JOB_ID = "guide_refresh_hdhomerun_cloud"
_EPISODE_NUMBER_RE = re.compile(r"^(\d+)\.(\d+)$")


def register(scheduler: AsyncIOScheduler) -> None:
    scheduler.add_job(
        refresh_hdhomerun_guide,
        "interval",
        seconds=REFRESH_INTERVAL_SECONDS,
        id=_JOB_ID,
        replace_existing=True,  # safe to re-register across app restarts / test sessions
        next_run_time=datetime.now(UTC),  # bootstrap: fetch once immediately, then on the interval
        max_instances=1,
        coalesce=True,
    )


async def _hdhomerun_settings_or_none() -> dict[str, Any] | None:
    row = await asyncio.to_thread(db.get_network_integration, "hdhomerun")
    return row["settings"] if row else None


def _parse_episode_number(raw: Any) -> tuple[int | None, int | None]:
    """HDHomeRun's EpisodeNumber is a raw string like "5.12" (season.episode)
    or sometimes a bare episode number. Best-effort parse; None/None on
    anything unrecognized rather than raising."""
    if not raw:
        return None, None
    match = _EPISODE_NUMBER_RE.match(str(raw).strip())
    if match:
        return int(match.group(1)), int(match.group(2))
    try:
        return None, int(str(raw).strip())
    except ValueError:
        return None, None


def _airing_to_row(channel_id: str, airing: dict[str, Any]) -> dict[str, Any] | None:
    start, end = airing.get("start"), airing.get("end")
    if start is None or end is None:
        return None
    season_number, episode_number = _parse_episode_number(airing.get("episode_number"))
    return {
        "channel_id": channel_id,
        "source_provider": SOURCE_PROVIDER,
        "external_program_id": airing.get("series_id"),
        "title": airing.get("title") or "",
        "episode_title": airing.get("episode_title"),
        "season_number": season_number,
        "episode_number": episode_number,
        "synopsis": airing.get("synopsis"),
        "start_ts": float(start),
        "end_ts": float(end),
        "original_air_date": airing.get("original_airdate"),
        "image_url": airing.get("image_url"),
        "is_new": 0,
        "category": None,
    }


def _sync_channels_and_guide(
    lineup: list[dict[str, Any]], full_guide: list[dict[str, Any]], job_start_ts: float
) -> None:
    channel_id_by_number: dict[str, str] = {}
    for channel in lineup:
        number = channel["channel_number"]
        if not number:
            continue
        existing = db.get_channel_by_number(number)
        channel_id = existing["id"] if existing else uuid.uuid4().hex
        db.upsert_channel(channel_id, number, channel.get("name") or number, channel.get("is_hd", False))
        channel_id_by_number[number] = channel_id

    rows_by_channel: dict[str, list[dict[str, Any]]] = {}
    for channel in full_guide:
        number = channel.get("channel_number", "")
        channel_id = channel_id_by_number.get(number)
        if channel_id is None:
            # Guide mentions a channel the lineup didn't (rare/transient) — don't drop its data.
            existing = db.get_channel_by_number(number)
            channel_id = existing["id"] if existing else uuid.uuid4().hex
            if existing is None:
                db.upsert_channel(channel_id, number, channel.get("channel_name") or number, False)
            channel_id_by_number[number] = channel_id
        for airing in channel.get("airings", []):
            row = _airing_to_row(channel_id, airing)
            if row is not None:
                rows_by_channel.setdefault(channel_id, []).append(row)

    delete_from_ts = job_start_ts - 4 * 3600
    for channel_id, rows in rows_by_channel.items():
        db.delete_future_guide_programs(channel_id, SOURCE_PROVIDER, delete_from_ts)
        db.upsert_guide_programs(rows)


async def refresh_hdhomerun_guide() -> None:
    """Scheduler job: pull SiliconDust's cloud guide and persist it."""
    settings = await _hdhomerun_settings_or_none()
    if settings is None or not hdhomerun_client.is_tuner_configured(settings):
        return

    job_start_ts = time.time()
    try:
        lineup = await hdhomerun_client.fetch_lineup(settings)
    except HDHomeRunError:
        logger.info("Tuner unreachable; skipping guide refresh this cycle", exc_info=True)
        return

    full_guide = await hdhomerun_client.fetch_full_guide(settings, "hdhomerun")
    if full_guide is None:
        logger.info("HDHomeRun cloud guide unavailable this cycle (no subscription / fetch failed)")
        return

    await asyncio.to_thread(_sync_channels_and_guide, lineup, full_guide, job_start_ts)
    await asyncio.to_thread(db.save_guide_provider_state, SOURCE_PROVIDER, datetime.now(UTC).isoformat())
    logger.info("Refreshed HDHomeRun cloud guide (%d channels)", len(full_guide))
