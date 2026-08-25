"""Rule expansion engine for the builtin DVR.

Expands recurring series and single-airing recording rules against stored
guide_programs into concrete scheduled_recordings.

Supports both:
1. HDHomeRun Cloud Schedule: Matched via SiliconDust SeriesID (external_program_id).
2. EPG / XMLTV Schedules: Matched via normalized title and episode metadata.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Any

from app.config import resolve_guide_provider_priority
from app.storage import db

logger = logging.getLogger(__name__)

DEFAULT_LOOKAHEAD_SECONDS = 14 * 24 * 3600  # 14 days
_WHITESPACE_RE = re.compile(r"\s+")


def normalize_title(title: str) -> str:
    """Normalize a show title for robust EPG matching across feeds."""
    return _WHITESPACE_RE.sub(" ", title.strip().lower())


def _channel_lookup_maps() -> tuple[dict[str, dict[str, Any]], dict[str, str], dict[str, str]]:
    """Return (channels_by_id, id_by_number, number_by_id)."""
    channels = db.list_channels(True)
    channels_by_id = {c["id"]: c for c in channels}
    id_by_number = {c["channel_number"]: c["id"] for c in channels if c.get("channel_number")}
    number_by_id = {c["id"]: c["channel_number"] for c in channels if c.get("channel_number")}
    return channels_by_id, id_by_number, number_by_id


_DEDUP_TOLERANCE_SECONDS = 300  # bucket width below must equal this — see _bucket()


def _bucket(ts: float) -> int:
    return int(ts // _DEDUP_TOLERANCE_SECONDS)


def _index_scheduled(
    s: dict[str, Any],
    by_channel_bucket: dict[tuple[str, int], list[dict[str, Any]]],
    by_rule_bucket: dict[tuple[str, int], list[dict[str, Any]]],
) -> None:
    b = _bucket(s["start_ts"])
    by_channel_bucket.setdefault((s["channel_id"], b), []).append(s)
    rule_id = s.get("rule_id")
    if rule_id:
        by_rule_bucket.setdefault((rule_id, b), []).append(s)


def _is_already_recorded_or_scheduled(
    rule_id: str,
    channel_id: str,
    start_ts: float,
    title: str,
    episode_title: str | None,
    season_number: int | None,
    episode_number: int | None,
    by_channel_bucket: dict[tuple[str, int], list[dict[str, Any]]],
    by_rule_bucket: dict[tuple[str, int], list[dict[str, Any]]],
    by_season_episode: dict[tuple[str, int, int], dict[str, Any]],
    by_episode_title: dict[tuple[str, str], dict[str, Any]],
) -> bool:
    """Check if this airing is already scheduled or recorded, via the
    prebuilt lookup structures (see expand_rules_sync)."""
    # Check scheduled recordings: bucket width == tolerance, so any match
    # within +/-300s falls in the same or an adjacent bucket.
    b = _bucket(start_ts)
    for offset in (-1, 0, 1):
        for s in by_channel_bucket.get((channel_id, b + offset), ()):
            if abs(s["start_ts"] - start_ts) < 300:
                return True
        for s in by_rule_bucket.get((rule_id, b + offset), ()):
            if abs(s["start_ts"] - start_ts) < 300:
                return True

    # Check already completed recordings
    norm_title = normalize_title(title)
    if (
        season_number is not None
        and episode_number is not None
        and (norm_title, season_number, episode_number) in by_season_episode
    ):
        return True
    if episode_title and (norm_title, normalize_title(episode_title)) in by_episode_title:
        return True

    return False


def _match_airing(rule: dict[str, Any], program: dict[str, Any]) -> bool:
    """Determine if a guide_program matches a recording rule."""
    rule_title = rule.get("title", "")
    rule_series_key = rule.get("series_match_key")
    program_ext_id = program.get("external_program_id")
    program_title = program.get("title", "")

    # 1. HDHomeRun SeriesID matching (for rules with SiliconDust SeriesID e.g. EP..., SH...)
    if rule_series_key and program_ext_id and program_ext_id == rule_series_key:
        return True

    # 2. Title matching (for XMLTV/EPG feeds or generic title rules)
    if rule_title and program_title:
        norm_rule = normalize_title(rule_title)
        norm_prog = normalize_title(program_title)
        if norm_rule == norm_prog:
            return True

    return False


def expand_rules_sync(lookahead_seconds: float = DEFAULT_LOOKAHEAD_SECONDS) -> list[dict[str, Any]]:
    """Synchronous rule expansion run against SQLite."""
    now = time.time()
    end_window = now + lookahead_seconds

    rules = db.list_recording_rules(provider="builtin")
    if not rules:
        return []

    channels_by_id, id_by_number, number_by_id = _channel_lookup_maps()
    all_channel_ids = list(channels_by_id.keys())
    if not all_channel_ids:
        return []

    # Fetch guide programs in window
    raw_programs = db.list_guide_programs(all_channel_ids, now - 3600, end_window)
    priority = resolve_guide_provider_priority()
    resolved_programs_by_channel = db.resolve_guide_programs(list(channels_by_id.values()), raw_programs, priority)

    existing_scheduled_raw = db.list_scheduled_recordings()
    existing_scheduled = [
        s for s in existing_scheduled_raw if s.get("status") in ("scheduled", "in_progress", "completed")
    ]
    existing_recordings = db.list_completed_recordings()

    by_season_episode: dict[tuple[str, int, int], dict[str, Any]] = {}
    by_episode_title: dict[tuple[str, str], dict[str, Any]] = {}
    for r in existing_recordings:
        norm_r_title = normalize_title(r.get("title", ""))
        s_num, e_num = r.get("season_number"), r.get("episode_number")
        if s_num is not None and e_num is not None:
            by_season_episode[(norm_r_title, s_num, e_num)] = r
        r_ep_title = r.get("episode_title")
        if r_ep_title:
            by_episode_title[(norm_r_title, normalize_title(r_ep_title))] = r

    by_channel_bucket: dict[tuple[str, int], list[dict[str, Any]]] = {}
    by_rule_bucket: dict[tuple[str, int], list[dict[str, Any]]] = {}
    for s in existing_scheduled:
        _index_scheduled(s, by_channel_bucket, by_rule_bucket)

    newly_scheduled: list[dict[str, Any]] = []

    for rule in rules:
        rule_id = rule["id"]
        rule_type = rule.get("type", "series")
        rule_channel = rule.get("channel_id")  # may be channel_id UUID or channel_number
        rule_channel_id = id_by_number.get(rule_channel, rule_channel) if rule_channel else None
        start_padding = rule.get("start_padding_seconds", 0)
        end_padding = rule.get("end_padding_seconds", 0)

        # Target channels to inspect for this rule
        if rule_channel_id and rule_channel_id in channels_by_id:
            target_channels = [rule_channel_id]
        else:
            target_channels = all_channel_ids

        for ch_id in target_channels:
            programs = resolved_programs_by_channel.get(ch_id, [])
            for prog in programs:
                start_ts = prog["start_ts"]
                end_ts = prog["end_ts"]

                # Must not have already ended
                if end_ts <= now:
                    continue

                # Single airing rule check (match specific start timestamp if given)
                if rule_type == "single" and rule.get("series_match_key"):
                    try:
                        rule_ts = float(rule["series_match_key"])
                        if abs(start_ts - rule_ts) > 300:
                            continue
                    except ValueError:
                        pass

                # Check if program matches rule
                if not _match_airing(rule, prog):
                    continue

                # Check deduplication (also covers the new-only "already
                # recorded this episode" check for series rules, since this
                # runs unconditionally regardless of new_only/is_new)
                if _is_already_recorded_or_scheduled(
                    rule_id,
                    ch_id,
                    start_ts,
                    prog["title"],
                    prog.get("episode_title"),
                    prog.get("season_number"),
                    prog.get("episode_number"),
                    by_channel_bucket,
                    by_rule_bucket,
                    by_season_episode,
                    by_episode_title,
                ):
                    continue

                padded_start = max(0.0, start_ts - start_padding)
                padded_end = end_ts + end_padding
                scheduled_id = f"sched_{rule_id[:8]}_{ch_id[:8]}_{int(start_ts)}"

                scheduled_entry = {
                    "id": scheduled_id,
                    "rule_id": rule_id,
                    "channel_id": ch_id,
                    "guide_program_id": prog.get("external_program_id"),
                    "title": prog.get("title") or rule.get("title", ""),
                    "episode_title": prog.get("episode_title"),
                    "season_number": prog.get("season_number"),
                    "episode_number": prog.get("episode_number"),
                    "synopsis": prog.get("synopsis"),
                    "image_url": prog.get("image_url"),
                    "original_air_date": prog.get("original_air_date"),
                    "category": prog.get("category"),
                    "start_ts": padded_start,
                    "end_ts": padded_end,
                    "status": "scheduled",
                    "recording_id": None,
                }

                db.upsert_scheduled_recording(scheduled_entry)
                newly_scheduled.append(scheduled_entry)
                _index_scheduled(scheduled_entry, by_channel_bucket, by_rule_bucket)

    logger.info("Rule expansion completed (%d new airings scheduled)", len(newly_scheduled))
    return newly_scheduled


async def expand_rules(lookahead_seconds: float = DEFAULT_LOOKAHEAD_SECONDS) -> list[dict[str, Any]]:
    """Asynchronous wrapper for expand_rules_sync."""
    return await asyncio.to_thread(expand_rules_sync, lookahead_seconds)
