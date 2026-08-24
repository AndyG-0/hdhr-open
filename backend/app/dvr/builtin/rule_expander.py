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
import uuid
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


def _is_already_recorded_or_scheduled(
    rule_id: str,
    channel_id: str,
    start_ts: float,
    title: str,
    episode_title: str | None,
    season_number: int | None,
    episode_number: int | None,
    existing_scheduled: list[dict[str, Any]],
    existing_recordings: list[dict[str, Any]],
) -> bool:
    """Check if this airing is already scheduled or recorded."""
    # Check scheduled recordings
    for s in existing_scheduled:
        if s.get("status") in ("scheduled", "in_progress", "completed"):
            if s.get("channel_id") == channel_id and abs(s["start_ts"] - start_ts) < 300:
                return True
            if s.get("rule_id") == rule_id and abs(s["start_ts"] - start_ts) < 300:
                return True

    # Check already completed recordings
    for r in existing_recordings:
        if r.get("status") == "completed":
            norm_r_title = normalize_title(r.get("title", ""))
            norm_title = normalize_title(title)
            if norm_r_title == norm_title:
                # Same episode number
                if (
                    season_number is not None
                    and episode_number is not None
                    and r.get("season_number") == season_number
                    and r.get("episode_number") == episode_number
                ):
                    return True
                # Same episode title
                if episode_title and r.get("episode_title") and r["episode_title"].strip().lower() == episode_title.strip().lower():
                    return True

    return False


def _match_airing(rule: dict[str, Any], program: dict[str, Any]) -> bool:
    """Determine if a guide_program matches a recording rule."""
    rule_type = rule.get("type", "series")
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

    existing_scheduled = db.list_scheduled_recordings()
    existing_recordings = db.list_recordings()

    newly_scheduled: list[dict[str, Any]] = []

    for rule in rules:
        rule_id = rule["id"]
        rule_type = rule.get("type", "series")
        rule_channel = rule.get("channel_id")  # may be channel_id UUID or channel_number
        rule_channel_id = id_by_number.get(rule_channel, rule_channel) if rule_channel else None
        start_padding = rule.get("start_padding_seconds", 0)
        end_padding = rule.get("end_padding_seconds", 0)
        new_only = bool(rule.get("new_only", 1))

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

                # Check new-only requirement for series rules
                if rule_type == "series" and new_only:
                    if prog.get("is_new") == 0:
                        # Check if we already recorded this episode
                        if _is_already_recorded_or_scheduled(
                            rule_id,
                            ch_id,
                            start_ts,
                            prog["title"],
                            prog.get("episode_title"),
                            prog.get("season_number"),
                            prog.get("episode_number"),
                            existing_scheduled,
                            existing_recordings,
                        ):
                            continue

                # Check deduplication
                if _is_already_recorded_or_scheduled(
                    rule_id,
                    ch_id,
                    start_ts,
                    prog["title"],
                    prog.get("episode_title"),
                    prog.get("season_number"),
                    prog.get("episode_number"),
                    existing_scheduled,
                    existing_recordings,
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
                existing_scheduled.append(scheduled_entry)

    logger.info("Rule expansion completed (%d new airings scheduled)", len(newly_scheduled))
    return newly_scheduled


async def expand_rules(lookahead_seconds: float = DEFAULT_LOOKAHEAD_SECONDS) -> list[dict[str, Any]]:
    """Asynchronous wrapper for expand_rules_sync."""
    return await asyncio.to_thread(expand_rules_sync, lookahead_seconds)
