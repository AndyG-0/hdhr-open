"""Periodic cleanup of historical guide data across all guide providers."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app import jobs
from app.config import effective_settings, resolve_timezone
from app.storage import db
from app.storage.cache import cache

logger = logging.getLogger(__name__)

JOB_ID = "guide_cleanup_old_programs"
CLEANUP_INTERVAL_SECONDS = 24 * 3600  # 24 hours (daily)


def get_start_of_today_ts(timezone_name: str = "UTC") -> float:
    """Return the unix epoch timestamp for 00:00:00 (start of today) in the given timezone."""
    tz = resolve_timezone(timezone_name)
    now = datetime.now(tz)
    start_of_today = datetime(now.year, now.month, now.day, tzinfo=tz)
    return start_of_today.timestamp()


async def cleanup_old_guide_programs() -> int:
    """Purge guide program airings that ended on or before the start of today."""
    app_settings = await asyncio.to_thread(effective_settings)
    tz_name = app_settings.get("timezone", "UTC")
    cutoff_ts = get_start_of_today_ts(tz_name)

    deleted_count = await asyncio.to_thread(db.delete_old_guide_programs, cutoff_ts)
    cache.delete_prefix("guide:")
    logger.info(
        "Cleaned up %d old guide program(s) ending on or before start of today (cutoff: %.0f, tz: %s)",
        deleted_count,
        cutoff_ts,
        tz_name,
    )
    return deleted_count


def register(scheduler: AsyncIOScheduler) -> None:
    """Register the daily guide cleanup job with APScheduler and the jobs registry."""
    jobs.register_scheduled_job(
        scheduler,
        job_id=JOB_ID,
        name="Old guide data cleanup",
        description="Purges historical guide program airings older than today across all guide providers.",
        func=cleanup_old_guide_programs,
        trigger="interval",
        seconds=CLEANUP_INTERVAL_SECONDS,
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
