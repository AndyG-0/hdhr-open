"""Auto-extend in-progress recordings that look like live sports.

A scheduled program's `end_ts` is a guess (the broadcast's advertised
runtime); a close or rain-delayed game routinely runs long. This module
periodically checks active captures nearing their scheduled end, and — if
they're heuristically sports and TheSportsDB can't confirm the game has
finished — pushes `end_ts` out by a few minutes so DVREngine.tick() doesn't
cut the recording off mid-game.

Deliberately best-effort: TheSportsDB's free tier has no obligation to know
about any given local/regional broadcast, so an unconfirmed status is
treated as "still in progress" (fail-safe toward over-recording, not
under-recording — see APP_SETTINGS_KEYS docs in app.config). Extension state
(each recording's original end time, for cap enforcement) lives in an
in-memory dict rather than the database: on a mid-game restart the cap
baseline just shifts forward, a graceful degradation for a feature that's
explicitly opt-in and best-effort.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import UTC, datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import resolve_sports_extension_enabled, resolve_sports_extension_max_minutes
from app.dvr.builtin.capture import capture_pipeline
from app.dvr.builtin.poster_lookup import classify_category
from app.integrations.thesportsdb import extract_matchup_teams, get_event_status
from app.storage import db

logger = logging.getLogger(__name__)

_JOB_ID = "sports_extension_check"
CHECK_INTERVAL_SECONDS = 300  # 5 minutes
LOOKAHEAD_SECONDS = 600  # only consider captures ending within 10 minutes
EXTENSION_SECONDS = 900  # extend by 15 minutes per tick

# recording_id -> original scheduled end_ts, seeded on first extension.
# Not persisted: see module docstring.
_original_end_by_recording: dict[str, float] = {}


def register(scheduler: AsyncIOScheduler) -> None:
    scheduler.add_job(
        check_and_extend_sports_recordings,
        "interval",
        seconds=CHECK_INTERVAL_SECONDS,
        id=_JOB_ID,
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )


async def check_and_extend_sports_recordings() -> None:
    if not resolve_sports_extension_enabled():
        return

    max_extension_seconds = resolve_sports_extension_max_minutes() * 60
    now = time.time()
    active_captures = await capture_pipeline.list_active_captures()
    active_ids = {c.recording_id for c in active_captures}

    for recording_id in list(_original_end_by_recording):
        if recording_id not in active_ids:
            del _original_end_by_recording[recording_id]

    for capture in active_captures:
        if capture.end_ts - now > LOOKAHEAD_SECONDS or capture.end_ts <= now:
            continue

        category = classify_category(capture.title, capture.episode_title, capture.category)
        if category != "sports":
            continue

        teams = extract_matchup_teams(capture.episode_title or capture.title)
        if len(teams) != 2:
            continue

        original_end = _original_end_by_recording.setdefault(capture.recording_id, capture.end_ts)
        cap_end = original_end + max_extension_seconds
        if capture.end_ts >= cap_end:
            continue

        try:
            event_date = datetime.fromtimestamp(capture.start_ts, tz=UTC).date()
            status = await get_event_status(teams[0], teams[1], event_date)
        except Exception:
            logger.debug("Sports status lookup failed for recording %s", capture.recording_id, exc_info=True)
            status = None

        if status == "finished":
            continue

        new_end = min(capture.end_ts + EXTENSION_SECONDS, cap_end)
        if new_end <= capture.end_ts:
            continue

        await capture_pipeline.update_active_capture(capture.recording_id, end_ts=new_end)
        await asyncio.to_thread(db.update_recording, capture.recording_id, end_ts=new_end)
        logger.info(
            "Extended sports recording %s (%s) to %s (status=%s)",
            capture.recording_id,
            capture.title,
            datetime.fromtimestamp(new_end, tz=UTC).isoformat(),
            status,
        )
