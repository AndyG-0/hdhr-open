"""DVREngine: orchestrates rule expansion, tuner allocation, capture execution,
and retention jobs for the builtin DVR.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.api._hdhomerun_settings import get_hdhomerun_settings
from app.dvr.builtin.capture import ActiveCapture, capture_pipeline
from app.dvr.builtin.retention import delete_local_recording, enforce_rule_retention_sync, run_full_retention_pass
from app.dvr.builtin.rule_expander import expand_rules
from app.dvr.builtin.tuner_allocator import tuner_allocator
from app.dvr.builtin.watch import finalize_capture_release, promote_existing_capture_for_schedule, reap_stale_watches
from app.integrations import hdhomerun_client
from app.storage import db

logger = logging.getLogger(__name__)

TICK_INTERVAL_SECONDS = 10
RULE_EXPANSION_INTERVAL_SECONDS = 900  # 15 minutes
RETENTION_INTERVAL_SECONDS = 3600  # 1 hour

# recover_on_startup() runs on every FastAPI lifespan startup, which includes
# uvicorn --reload respawning the worker process (not just a genuine crash
# restart) - a live-watch capture that's only seconds old and still actively
# writing must not be mistaken for a dangling leftover just because a new
# worker process happens to be doing the check.
ORPHAN_CAPTURE_GRACE_SECONDS = 15


def _capture_file_is_still_growing(file_path: str | None) -> bool:
    if not file_path:
        return False
    p = Path(file_path)
    if not p.exists():
        return False
    return (time.time() - p.stat().st_mtime) < ORPHAN_CAPTURE_GRACE_SECONDS


class DVREngine:
    """Coordinates scheduled recordings, active captures, and retention."""

    def __init__(self) -> None:
        self._running = False
        self._lock = asyncio.Lock()

    async def recover_on_startup(self) -> None:
        """Clean up dangling in-progress DB records from prior process crashes."""
        all_recs = await asyncio.to_thread(db.list_recordings)
        dangling_recs = [r for r in all_recs if r.get("status") == "recording"]
        for r in dangling_recs:
            rec_id = r["id"]
            if r.get("is_temporary"):
                if _capture_file_is_still_growing(r.get("file_path")):
                    logger.info("Startup recovery: leaving live-watch capture [%s] alone - still actively writing", rec_id)
                    continue
                # A live-watch auto-capture that was never promoted before the
                # process died - discard it like any other unpromoted watch
                # session rather than finalizing it as a permanent recording.
                logger.info("Startup recovery: discarding orphaned live-watch capture [%s]", rec_id)
                await delete_local_recording(rec_id, reason="startup recovery: orphaned live-watch capture from a prior process crash")
                continue
            file_path = r.get("file_path")
            file_size = 0
            if file_path:
                p = Path(file_path)
                if p.exists():
                    file_size = p.stat().st_size

            status = "completed" if file_size >= 10240 else "failed"
            logger.info("Startup recovery: finalized dangling recording [%s] as %s", rec_id, status)
            await asyncio.to_thread(
                db.update_recording,
                rec_id,
                status=status,
                file_size_bytes=file_size,
            )

        await asyncio.to_thread(db.mark_in_progress_scheduled_recordings_interrupted)

    async def tick(self) -> None:
        """Main engine tick: stops finished captures and launches ready scheduled recordings."""
        now = time.time()
        settings = await get_hdhomerun_settings()

        if not hdhomerun_client.is_tuner_configured(settings):
            return

        # 1. Check and stop active captures whose end time has passed. A
        # still-temporary (never promoted) live-watch capture hitting its
        # safety-cap end_ts is discarded like any other unpromoted watch
        # session, not finalized as a permanent recording.
        active_captures = await capture_pipeline.list_active_captures()
        for capture in active_captures:
            if now >= capture.end_ts:
                row = await asyncio.to_thread(db.get_recording, capture.recording_id)
                if row and row.get("is_temporary"):
                    await finalize_capture_release(capture.recording_id, capture.channel_number)
                    continue
                res = await capture_pipeline.stop_capture(capture.recording_id)
                await tuner_allocator.release_channel(capture.channel_number)
                if res and res.get("rule_id"):
                    rule = await asyncio.to_thread(db.get_recording_rule, res["rule_id"])
                    if rule and rule.get("max_episodes_to_keep"):
                        await asyncio.to_thread(
                            enforce_rule_retention_sync,
                            res["rule_id"],
                            rule["max_episodes_to_keep"],
                        )

        # 1b. Reap live-watch captures whose client stopped heartbeating
        # (crashed tab, lost network, force-closed browser).
        await reap_stale_watches()

        # 2. Check scheduled recordings ready to start
        scheduled_list = await asyncio.to_thread(db.list_scheduled_recordings, "scheduled")
        channels = await asyncio.to_thread(db.list_channels, True)
        channel_by_id = {c["id"]: c for c in channels}
        channel_by_number = {c["channel_number"]: c for c in channels if c.get("channel_number")}

        for sched in scheduled_list:
            start_ts = sched["start_ts"]
            end_ts = sched["end_ts"]

            # If recording has already expired, mark missed
            if end_ts <= now:
                await asyncio.to_thread(db.update_scheduled_recording_status, sched["id"], "missed")
                continue

            # If it's time to start
            if start_ts <= now < end_ts:
                ch_id = sched["channel_id"]
                channel_obj = channel_by_id.get(ch_id) or channel_by_number.get(ch_id)
                ch_num = channel_obj["channel_number"] if channel_obj else ch_id
                ch_name = channel_obj["name"] if channel_obj else ch_num

                # A live-watch session may already be capturing this channel -
                # attach the schedule to it instead of double-booking a tuner.
                # Routed through get_or_start_capture (shared with
                # watch.start_watch) so a viewer tuning in at the same moment
                # this scheduled recording starts can't race it into spawning
                # a second tuner/ffmpeg for the same channel.
                recording_id = uuid.uuid4().hex

                async def _create_capture() -> ActiveCapture | None:
                    allocated = await tuner_allocator.acquire_tuner(recording_id, ch_num, settings)
                    if not allocated:
                        logger.warning(
                            "Tuner busy; postponing scheduled recording '%s' on ch %s",
                            sched["title"],
                            ch_num,
                        )
                        return None

                    capture = await capture_pipeline.start_capture(
                        recording_id=recording_id,
                        channel_number=ch_num,
                        channel_name=ch_name,
                        title=sched["title"],
                        start_ts=start_ts,
                        end_ts=end_ts,
                        settings=settings,
                        scheduled_id=sched["id"],
                        rule_id=sched.get("rule_id"),
                        episode_title=sched.get("episode_title"),
                        season_number=sched.get("season_number"),
                        episode_number=sched.get("episode_number"),
                        synopsis=sched.get("synopsis"),
                        original_air_date=sched.get("original_air_date"),
                        category=sched.get("category"),
                        image_url=sched.get("image_url"),
                    )
                    if not capture:
                        await tuner_allocator.release_tuner(recording_id)
                        logger.error("Failed to start capture process for recording %s", recording_id)
                    return capture

                capture, created = await capture_pipeline.get_or_start_capture(ch_num, _create_capture)
                if capture is None:
                    continue

                if not created:
                    attached = await promote_existing_capture_for_schedule(
                        capture,
                        scheduled_id=sched["id"],
                        rule_id=sched.get("rule_id"),
                        title=sched["title"],
                        episode_title=sched.get("episode_title"),
                        end_ts=end_ts,
                        settings=settings,
                        season_number=sched.get("season_number"),
                        episode_number=sched.get("episode_number"),
                        synopsis=sched.get("synopsis"),
                        image_url=sched.get("image_url"),
                        original_air_date=sched.get("original_air_date"),
                        category=sched.get("category"),
                    )
                    if not attached:
                        logger.error(
                            "Failed to attach scheduled recording '%s' to existing capture on ch %s",
                            sched["title"],
                            ch_num,
                        )


dvr_engine = DVREngine()


def register(scheduler: AsyncIOScheduler) -> None:
    """Register DVR engine background jobs with APScheduler."""
    scheduler.add_job(
        dvr_engine.tick,
        "interval",
        seconds=TICK_INTERVAL_SECONDS,
        id="builtin_dvr_engine_tick",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )

    scheduler.add_job(
        expand_rules,
        "interval",
        seconds=RULE_EXPANSION_INTERVAL_SECONDS,
        id="builtin_dvr_rule_expansion",
        replace_existing=True,
        next_run_time=datetime.now(UTC),
        max_instances=1,
        coalesce=True,
    )

    scheduler.add_job(
        run_full_retention_pass,
        "interval",
        seconds=RETENTION_INTERVAL_SECONDS,
        id="builtin_dvr_retention_pass",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
