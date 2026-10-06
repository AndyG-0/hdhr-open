"""Series-recording fallback for free HDHomeRun accounts.

SiliconDust's auto-record (series) recording rules require a full guide DVR
subscription — a free account's `add_recording_rule` call for a series rule
still returns 200 OK and the rule still shows up in `recording_rules.json`,
but the upstream DVR engine silently never executes it (see
`hdhomerun_client.resolve_account_tier`'s docstring for how a free account is
inferred). SiliconDust's own docs (info.hdhomerun.com/info/app:recording)
confirm single/one-time "record this airing" recordings have no subscription
requirement — only auto-record is gated.

So a free account's "series" recordings can still end up on SiliconDust's own
DVR engine (visible in the official app too, not just here) by never calling
the broken auto-record API at all: `app.api.dvr_rules` tracks each such
"series intent" locally instead (recording_rules rows with
provider="hdhomerun_series_watch", the real SiliconDust SeriesID kept in
series_match_key), and this module periodically creates a single one-time
(DateTimeOnly) official recording rule for just its next upcoming occurrence
— which free accounts actually can record. Once that occurrence airs (or is
superseded), the next run schedules the one after it.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.api._dvr_shared import _get_hdhomerun_settings_safe
from app.integrations import hdhomerun_client
from app.storage import db

logger = logging.getLogger(__name__)

_JOB_ID = "hdhomerun_series_watch_sync"
# Hourly: frequent enough that a watch is normally picked up with at least a
# day of lead time before air (insufficient lead time was itself a secondary
# suspect in one of the two real-world misses that led to this module), well
# inside the free tier's scheduling ceiling below, without hammering
# SiliconDust's API.
CHECK_INTERVAL_SECONDS = 3600
# Stay safely inside the documented free-tier "up to 3 days in advance"
# scheduling ceiling (vs. 14 for full subscribers) — see
# hdhomerun_client._FREE_TIER_GUIDE_WINDOW_THRESHOLD_DAYS.
_MAX_ADVANCE_DAYS = 2.5
# Don't bother creating a one-time rule for something airing this soon;
# there's little point and it's an easy way to spam the API every hour on a
# recurring daily show instead of catching it earlier in its window.
_MIN_ADVANCE_SECONDS = 1800
_EXISTING_RULE_MATCH_TOLERANCE_SECONDS = 300


def register(scheduler: AsyncIOScheduler) -> None:
    scheduler.add_job(
        sync_series_watches,
        "interval",
        seconds=CHECK_INTERVAL_SECONDS,
        id=_JOB_ID,
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )


def _find_next_occurrence(watch: dict[str, Any]) -> dict[str, Any] | None:
    """The earliest upcoming hdhomerun_cloud-sourced airing matching this
    watch's SeriesID, within the free tier's schedulable window."""
    series_id = watch.get("series_match_key")
    if not series_id:
        return None

    now = time.time()
    earliest = now + _MIN_ADVANCE_SECONDS
    window_end = now + _MAX_ADVANCE_DAYS * 86400

    channels = db.list_channels(True)
    channel_number = watch.get("channel_id")
    id_by_number = {c["channel_number"]: c["id"] for c in channels if c.get("channel_number")}
    ch_ids = [id_by_number[channel_number]] if channel_number and channel_number in id_by_number else [
        c["id"] for c in channels
    ]

    programs = db.list_guide_programs(ch_ids, earliest, window_end)
    candidates = [
        p
        for p in programs
        if p.get("source_provider") == "hdhomerun_cloud"
        and p.get("external_program_id") == series_id
        and p["start_ts"] >= earliest
        and (not watch.get("new_only") or p.get("is_new"))
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda p: p["start_ts"])


def _already_scheduled(existing_official_rules: list[dict[str, Any]], series_id: str, start_ts: float) -> bool:
    for r in existing_official_rules:
        if r.get("SeriesID") != series_id:
            continue
        rule_start = r.get("DateTimeOnly")
        if rule_start and abs(rule_start - start_ts) <= _EXISTING_RULE_MATCH_TOLERANCE_SECONDS:
            return True
    return False


async def sync_series_watches() -> None:
    watches = db.list_recording_rules("hdhomerun_series_watch")
    if not watches:
        return

    settings = await _get_hdhomerun_settings_safe()
    if not (hdhomerun_client.is_dvr_configured(settings) or hdhomerun_client.is_tuner_configured(settings)):
        return

    try:
        existing_official_rules = await hdhomerun_client.fetch_dvr_recording_rules(settings)
    except Exception as exc:
        logger.warning("hdhomerun_series_watch: could not fetch official rules, skipping this run: %s", exc)
        return

    for watch in watches:
        occurrence = _find_next_occurrence(watch)
        if occurrence is None:
            continue

        series_id = watch["series_match_key"]
        start_ts = occurrence["start_ts"]
        if _already_scheduled(existing_official_rules, series_id, start_ts):
            continue

        channel = db.get_channel(occurrence["channel_id"])
        channel_number = channel.get("channel_number") if channel else watch.get("channel_id")

        try:
            await hdhomerun_client.add_recording_rule(
                settings,
                {
                    "series_id": series_id,
                    "channel": channel_number,
                    "date_time": int(start_ts),
                    "start_padding": watch.get("start_padding_seconds"),
                    "end_padding": watch.get("end_padding_seconds"),
                },
            )
            logger.info(
                "hdhomerun_series_watch: scheduled next occurrence of %r (SeriesID %s) at %s on channel %s",
                watch.get("title"),
                series_id,
                int(start_ts),
                channel_number,
            )
        except hdhomerun_client.HDHomeRunError as exc:
            logger.warning(
                "hdhomerun_series_watch: could not schedule next occurrence of %r: %s", watch.get("title"), exc
            )
