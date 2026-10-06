"""DVR recording rules (create/list/update/delete), for both the builtin and
official HDHomeRun DVR engines. Mounted into dvr.py's router via
include_router, so it inherits that router's prefix/auth dependency.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field

from app.api._dvr_shared import _get_hdhomerun_settings_safe
from app.async_utils import run_in_background
from app.config import resolve_dvr_server_priority
from app.dvr.builtin.rule_expander import expand_rules
from app.integrations import hdhomerun_client, hdhomerun_series_watch
from app.storage import db

logger = logging.getLogger(__name__)

router = APIRouter()


class RecordingRuleCreateRequest(BaseModel):
    series_id: str | None = None
    date_time: int | None = None
    channel: str | None = None
    recent_only: bool | None = None
    start_padding: int | None = None
    end_padding: int | None = None
    max_episodes_to_keep: int | None = Field(default=None, ge=1)
    server: str | None = None
    # Builtin-DVR-only: a caller-supplied title (bypasses guide lookup, so a
    # rule can be created with no backing airing yet), an alternate title
    # match mode, and an inclusion keyword filter checked against episode
    # description/subtitle/category. Not supported by the official
    # HDHomeRun DVR API.
    title: str | None = None
    title_match_mode: str | None = None
    keyword_query: str | None = None
    # 'default' (follow the global comskip_mode setting), 'always', or
    # 'never' — see app.dvr.builtin.comskip.resolve_comskip_enabled.
    comskip_override: str | None = None


class RecordingRuleUpdateRequest(BaseModel):
    series_id: str | None = None
    date_time: int | None = None
    channel: str | None = None
    recent_only: bool | None = None
    start_padding: int | None = None
    end_padding: int | None = None
    max_episodes_to_keep: int | None = Field(default=None, ge=1)
    server: str | None = None
    title: str | None = None
    title_match_mode: str | None = None
    keyword_query: str | None = None
    comskip_override: str | None = None


def _format_local_rule(rule: dict[str, Any]) -> dict[str, Any]:
    """Formats a `recording_rules` row (provider "builtin" or
    "hdhomerun_series_watch" - both are local SQLite rows, just owned by
    different engines) into the same shape official HDHomeRun DVR rules use.
    """
    rule_type = rule.get("type", "series")
    series_key = rule.get("series_match_key")
    dt_only = None
    if rule_type == "single" and series_key:
        try:
            dt_only = int(float(series_key))
        except ValueError:
            pass

    return {
        "RecordingRuleID": rule["id"],
        "SeriesID": series_key if series_key and not dt_only else (series_key or "auto"),
        "Title": rule.get("title", ""),
        "DateTimeOnly": dt_only,
        "ChannelOnly": rule.get("channel_id"),
        "RecentOnly": 1 if rule.get("new_only") else 0,
        "StartPadding": rule.get("start_padding_seconds", 0),
        "EndPadding": rule.get("end_padding_seconds", 0),
        "MaxEpisodesToKeep": rule.get("max_episodes_to_keep"),
        "TitleMatchMode": rule.get("title_match_mode") or "exact",
        "KeywordQuery": rule.get("keyword_query"),
        "ComskipOverride": rule.get("comskip_override") or "default",
        "FallbackReason": rule.get("fallback_reason"),
        "fallback_reason": rule.get("fallback_reason"),
        "Provider": rule.get("provider") or "builtin",
        "provider": rule.get("provider") or "builtin",
    }


@router.get("/recording-rules")
async def list_recording_rules():
    settings = await _get_hdhomerun_settings_safe()
    results: list[dict[str, Any]] = []

    # 1. Builtin recording rules from SQLite
    builtin_rules = await asyncio.to_thread(db.list_recording_rules, "builtin")
    for rule in builtin_rules:
        results.append(_format_local_rule(rule))

    # 2. Free-tier "series watch" intents tracked locally because the
    # official engine's auto-record API doesn't work for this account (see
    # app.integrations.hdhomerun_series_watch) - each one periodically
    # materializes as a real single-airing rule on the official engine below,
    # but the watch's own standing intent is always local.
    watch_rules = await asyncio.to_thread(db.list_recording_rules, "hdhomerun_series_watch")
    for rule in watch_rules:
        results.append(_format_local_rule(rule))

    # 3. Official HDHomeRun DVR recording rules (if configured)
    if hdhomerun_client.is_dvr_configured(settings) or hdhomerun_client.is_tuner_configured(settings):
        try:
            official_rules = await hdhomerun_client.fetch_dvr_recording_rules(settings)
            # Exclude duplicate IDs if any
            existing_ids = {r["RecordingRuleID"] for r in results}
            for off in official_rules:
                if off.get("RecordingRuleID") not in existing_ids:
                    off_copy = dict(off)
                    off_copy.setdefault("Provider", "hdhomerun")
                    off_copy.setdefault("provider", "hdhomerun")
                    results.append(off_copy)
        except Exception as exc:
            logger.warning("Could not fetch official DVR recording rules: %s", exc)

    return results


def _lookup_guide_title(series_id: str | None, channel: str | None, date_time: int | None) -> str:
    """Find a friendly show title in stored guide_programs."""
    channels = db.list_channels(True)
    all_ch_ids = [c["id"] for c in channels]
    id_by_number = {c["channel_number"]: c["id"] for c in channels if c.get("channel_number")}
    target_ch_id = id_by_number.get(channel) if channel else None
    if channel and target_ch_id is None:
        logger.warning("_lookup_guide_title: channel %r did not match any known channel_number", channel)

    if date_time:
        # A channel was requested but didn't resolve to a real one - don't
        # widen to every channel, since that can pick up a same-time airing
        # on an unrelated channel and mislabel the rule.
        ch_list = [target_ch_id] if target_ch_id else (all_ch_ids if not channel else [])
        programs = db.list_guide_programs(ch_list, date_time - 300, date_time + 300)
        for p in programs:
            if abs(p["start_ts"] - date_time) < 300 and p.get("title"):
                return p["title"]

    if series_id and series_id != "auto":
        programs = db.list_guide_programs(all_ch_ids, time.time() - 86400, time.time() + 14 * 86400)
        for p in programs:
            if p.get("external_program_id") == series_id and p.get("title"):
                return p["title"]

    if channel:
        return f"Channel {channel}"
    return series_id or "Untitled Recording"


def _lookup_hdhomerun_series_id(channel: str | None, date_time: int | None, title: str | None) -> str | None:
    """Find a SiliconDust SeriesID from hdhomerun_cloud guide programs.

    A caller-supplied `channel` locks the search to that one channel. If it
    doesn't resolve to a known channel_number, this must NOT widen to every
    channel: a same-titled show airing on a different channel/affiliate can
    carry a different SeriesID (SiliconDust IDs are often market-specific),
    and submitting that mismatched SeriesID alongside the original
    ChannelOnly would create a rule that can never match a real airing and
    silently never records anything.
    """
    channels = db.list_channels(True)
    all_ch_ids = [c["id"] for c in channels]
    id_by_number = {c["channel_number"]: c["id"] for c in channels if c.get("channel_number")}
    target_ch_id = id_by_number.get(channel) if channel else None

    if channel and target_ch_id is None:
        logger.warning(
            "_lookup_hdhomerun_series_id: channel %r did not match any known channel_number; "
            "refusing to search other channels for a SeriesID",
            channel,
        )
        return None

    ch_list = [target_ch_id] if target_ch_id else all_ch_ids

    # 1. Match by channel and airing timestamp
    if date_time:
        programs = db.list_guide_programs(ch_list, date_time - 300, date_time + 300)
        for p in programs:
            if p.get("source_provider") == "hdhomerun_cloud" and p.get("external_program_id"):
                if abs(p["start_ts"] - date_time) <= 120:
                    logger.info(
                        "_lookup_hdhomerun_series_id: resolved SeriesID %s from %r on channel %r via timestamp match",
                        p["external_program_id"],
                        p.get("title"),
                        channel,
                    )
                    return p["external_program_id"]

    # 2. Match by channel and title
    if title:
        norm_target = title.strip().lower()
        programs = db.list_guide_programs(ch_list, time.time() - 86400, time.time() + 7 * 86400)
        for p in programs:
            if p.get("source_provider") == "hdhomerun_cloud" and p.get("external_program_id") and p.get("title"):
                norm_p = p["title"].strip().lower()
                if norm_target == norm_p or norm_target in norm_p or norm_p in norm_target:
                    logger.info(
                        "_lookup_hdhomerun_series_id: resolved SeriesID %s from %r on channel %r via title match",
                        p["external_program_id"],
                        p.get("title"),
                        channel,
                    )
                    return p["external_program_id"]

    logger.info(
        "_lookup_hdhomerun_series_id: no SeriesID found for channel=%r date_time=%r title=%r",
        channel,
        date_time,
        title,
    )
    return None


async def _resolve_hdhomerun_series_id(
    series_id: str | None, channel: str | None, date_time: int | None, title: str | None
) -> str | None:
    """Return `series_id` as-is if it's already a real SiliconDust SeriesID,
    otherwise try to resolve one from the hdhomerun_cloud guide."""
    if series_id and series_id != "auto":
        return series_id
    return await asyncio.to_thread(_lookup_hdhomerun_series_id, channel, date_time, title)


async def _create_hdhomerun_recording_rule(
    settings: dict[str, Any],
    *,
    series_id: str | None,
    channel: str | None,
    date_time: int | None,
    recent_only: bool | None,
    start_padding: int | None,
    end_padding: int | None,
) -> None:
    rule_data: dict[str, Any] = {
        "series_id": series_id,
        "channel": channel,
        "date_time": date_time,
        "recent_only": recent_only,
        "start_padding": start_padding,
        "end_padding": end_padding,
    }
    await hdhomerun_client.add_recording_rule(settings, rule_data)


async def _create_hdhomerun_series_watch_rule(
    *,
    series_id: str,
    channel: str | None,
    recent_only: bool | None,
    start_padding: int | None,
    end_padding: int | None,
    title: str | None,
) -> dict[str, Any]:
    """Track a free-account series intent locally instead of submitting a
    real auto-record rule the official DVR engine would silently never
    execute - see app.integrations.hdhomerun_series_watch."""
    rule_id = f"rule_{uuid.uuid4().hex[:12]}"
    resolved_title = title or await asyncio.to_thread(_lookup_guide_title, series_id, channel, None)

    rule_entry = {
        "id": rule_id,
        "provider": "hdhomerun_series_watch",
        "type": "series",
        "title": resolved_title or "Untitled",
        "series_match_key": series_id,
        "channel_id": channel,
        "start_padding_seconds": start_padding or 0,
        "end_padding_seconds": end_padding or 0,
        "new_only": 1 if recent_only else 0,
        "priority": 0,
    }
    await asyncio.to_thread(db.create_recording_rule, rule_entry)
    # Don't make the user wait up to an hour for the next scheduled sync to
    # pick up the first occurrence.
    run_in_background(hdhomerun_series_watch.sync_series_watches())
    return rule_entry


async def _create_builtin_recording_rule(
    *,
    series_id: str | None,
    date_time: int | None,
    channel: str | None,
    recent_only: bool | None,
    start_padding: int | None,
    end_padding: int | None,
    max_episodes_to_keep: int | None,
    title: str | None,
    title_match_mode: str | None,
    keyword_query: str | None,
    fallback_reason: str | None = None,
    comskip_override: str | None = None,
) -> dict[str, Any]:
    rule_id = f"rule_{uuid.uuid4().hex[:12]}"
    rule_type = "single" if date_time is not None else "series"

    resolved_title = title or await asyncio.to_thread(_lookup_guide_title, series_id, channel, date_time)
    series_match_key = (
        str(date_time)
        if rule_type == "single" and date_time
        else (series_id if series_id and series_id != "auto" else resolved_title)
    )

    rule_entry = {
        "id": rule_id,
        "provider": "builtin",
        "type": rule_type,
        "title": resolved_title or "Untitled",
        "series_match_key": series_match_key,
        "channel_id": channel,
        "start_padding_seconds": start_padding or 0,
        "end_padding_seconds": end_padding or 0,
        "new_only": 1 if recent_only else 0,
        "priority": 0,
        "max_episodes_to_keep": max_episodes_to_keep,
        "title_match_mode": title_match_mode if title_match_mode == "contains" else "exact",
        "keyword_query": keyword_query,
        "fallback_reason": fallback_reason,
        "comskip_override": comskip_override if comskip_override in ("always", "never") else "default",
    }

    await asyncio.to_thread(db.create_recording_rule, rule_entry)
    run_in_background(expand_rules())
    return rule_entry


async def _attempt_migrate_builtin_fallback_rule(rule: dict[str, Any], settings: dict[str, Any]) -> bool:
    """Retry resolving a SiliconDust SeriesID for a builtin rule that fell back
    from the official HDHomeRun DVR due to a missing SeriesID, and migrate it
    to that engine if one can now be found. Returns True if migrated."""
    if rule.get("title_match_mode") == "contains" or rule.get("keyword_query"):
        return False  # keyword/contains matching has no official-DVR equivalent

    date_time: int | None = None
    series_id: str | None = None
    series_match_key = rule.get("series_match_key")
    if rule.get("type") == "single" and series_match_key:
        with contextlib.suppress(ValueError, TypeError):
            date_time = int(float(series_match_key))
    elif series_match_key and series_match_key != rule.get("title"):
        series_id = series_match_key

    channel = rule.get("channel_id")
    title = rule.get("title")

    resolved_series_id = await _resolve_hdhomerun_series_id(series_id, channel, date_time, title)
    if not resolved_series_id:
        return False

    # A series (auto-record) rule would be silently accepted and never
    # executed on a free account - see
    # app.integrations.hdhomerun_series_watch. Single/one-time rules
    # (date_time set) aren't gated, so only the series case needs the detour.
    if date_time is None and hdhomerun_client.resolve_account_tier() == "free":
        await _create_hdhomerun_series_watch_rule(
            series_id=resolved_series_id,
            channel=channel,
            recent_only=bool(rule.get("new_only")),
            start_padding=rule.get("start_padding_seconds"),
            end_padding=rule.get("end_padding_seconds"),
            title=title,
        )
        await asyncio.to_thread(db.delete_recording_rule, rule["id"])
        await asyncio.to_thread(db.delete_scheduled_recordings_for_rule, rule["id"])
        logger.info(
            "Reconciliation: migrated fallback rule %r from builtin to a hdhomerun_series_watch "
            "(free-tier account, SeriesID now available)",
            rule.get("title"),
        )
        return True

    try:
        await _create_hdhomerun_recording_rule(
            settings,
            series_id=resolved_series_id,
            channel=channel,
            date_time=date_time,
            recent_only=bool(rule.get("new_only")),
            start_padding=rule.get("start_padding_seconds"),
            end_padding=rule.get("end_padding_seconds"),
        )
    except hdhomerun_client.HDHomeRunError as exc:
        logger.info(
            "Reconciliation: found a SeriesID for fallback rule %r but official DVR still rejected it: %s",
            rule.get("title"),
            exc,
        )
        return False

    await asyncio.to_thread(db.delete_recording_rule, rule["id"])
    await asyncio.to_thread(db.delete_scheduled_recordings_for_rule, rule["id"])
    logger.info(
        "Reconciliation: migrated fallback rule %r from builtin to the official HDHomeRun DVR "
        "now that a SeriesID is available",
        rule.get("title"),
    )
    return True


async def reconcile_hdhomerun_fallback_rules() -> None:
    """Retry builtin rules that fell back from the official HDHomeRun DVR
    engine because no SiliconDust SeriesID could be resolved yet. Intended to
    be called after each guide refresh: the cloud guide's window advances
    over time (bounded by SiliconDust's subscription-tier ceiling), so a
    rule stuck on the weaker builtin matcher at creation time can often be
    promoted to the official engine once the relevant airing's SeriesID
    actually shows up.
    """
    settings = await _get_hdhomerun_settings_safe()
    if not (hdhomerun_client.is_dvr_configured(settings) or hdhomerun_client.is_tuner_configured(settings)):
        return

    rules = await asyncio.to_thread(db.list_recording_rules, "builtin")
    fallback_rules = [r for r in rules if r.get("fallback_reason") == "guide_series_id_missing"]
    if not fallback_rules:
        return

    migrated_any = False
    for rule in fallback_rules:
        try:
            if await _attempt_migrate_builtin_fallback_rule(rule, settings):
                migrated_any = True
        except Exception:
            logger.warning("Reconciliation: error retrying fallback rule %r", rule.get("title"), exc_info=True)

    if migrated_any:
        run_in_background(expand_rules())


@router.post("/recording-rules")
async def create_recording_rule(payload: RecordingRuleCreateRequest, response: Response = None):
    settings = await _get_hdhomerun_settings_safe()
    priority = resolve_dvr_server_priority()
    preferred_server = payload.server if payload.server in ("builtin", "hdhomerun") else None

    # Keyword/contains matching is a builtin-only concept - the official
    # HDHomeRun DVR API has no equivalent, and silently dropping the filter
    # would make the rule over-record.
    is_keyword_rule = bool(payload.keyword_query) or payload.title_match_mode == "contains"
    if is_keyword_rule and preferred_server == "hdhomerun":
        raise HTTPException(
            status_code=400, detail="Keyword/contains-match rules are only supported by the builtin DVR"
        )

    target_servers = [preferred_server] if preferred_server else (["builtin"] if is_keyword_rule else list(priority))

    fallback_reason: str | None = None

    for target_server in target_servers:
        if target_server == "hdhomerun":
            if hdhomerun_client.is_dvr_configured(settings) or hdhomerun_client.is_tuner_configured(settings):
                series_id = await _resolve_hdhomerun_series_id(
                    payload.series_id, payload.channel, payload.date_time, payload.title
                )

                # A series (auto-record) rule on a free HDHomeRun account is
                # accepted by SiliconDust's API but never actually executed -
                # see app.integrations.hdhomerun_series_watch. Single/one-time
                # rules (date_time set) have no such restriction, so only
                # series rules need the detour. "unknown" tier (no cached
                # cloud guide data yet) falls through to the normal attempt
                # below rather than guessing.
                if payload.date_time is None and hdhomerun_client.resolve_account_tier() == "free":
                    if series_id and series_id != "auto":
                        await _create_hdhomerun_series_watch_rule(
                            series_id=series_id,
                            channel=payload.channel,
                            recent_only=payload.recent_only,
                            start_padding=payload.start_padding,
                            end_padding=payload.end_padding,
                            title=payload.title,
                        )
                        return await list_recording_rules()
                    # No SeriesID to track a watch against either - fall back
                    # to builtin same as the no-SeriesID case below.
                    fallback_reason = "guide_series_id_missing"
                    continue

                try:
                    await _create_hdhomerun_recording_rule(
                        settings,
                        series_id=series_id,
                        channel=payload.channel,
                        date_time=payload.date_time,
                        recent_only=payload.recent_only,
                        start_padding=payload.start_padding,
                        end_padding=payload.end_padding,
                    )
                    return await list_recording_rules()
                except hdhomerun_client.HDHomeRunError as exc:
                    logger.info("Official DVR rejected rule creation (%s); falling back to Built-in DVR", exc)
                    fallback_reason = (
                        "guide_series_id_missing"
                        if ("SeriesID" in str(exc) or not series_id or series_id == "auto")
                        else str(exc)
                    )
                    continue
            elif preferred_server == "hdhomerun":
                raise HTTPException(status_code=400, detail="HDHomeRun DVR is not configured")

        elif target_server == "builtin" or fallback_reason is not None:
            await _create_builtin_recording_rule(
                series_id=payload.series_id,
                date_time=payload.date_time,
                channel=payload.channel,
                recent_only=payload.recent_only,
                start_padding=payload.start_padding,
                end_padding=payload.end_padding,
                max_episodes_to_keep=payload.max_episodes_to_keep,
                title=payload.title,
                title_match_mode=payload.title_match_mode,
                keyword_query=payload.keyword_query,
                fallback_reason=fallback_reason,
                comskip_override=payload.comskip_override,
            )

            if fallback_reason and response is not None:
                response.headers["X-DVR-Fallback"] = "true"
                response.headers["X-DVR-Fallback-Reason"] = fallback_reason

            return await list_recording_rules()

    if fallback_reason is not None:
        await _create_builtin_recording_rule(
            series_id=payload.series_id,
            date_time=payload.date_time,
            channel=payload.channel,
            recent_only=payload.recent_only,
            start_padding=payload.start_padding,
            end_padding=payload.end_padding,
            max_episodes_to_keep=payload.max_episodes_to_keep,
            title=payload.title,
            title_match_mode=payload.title_match_mode,
            keyword_query=payload.keyword_query,
            fallback_reason=fallback_reason,
            comskip_override=payload.comskip_override,
        )
        if response is not None:
            response.headers["X-DVR-Fallback"] = "true"
            response.headers["X-DVR-Fallback-Reason"] = fallback_reason
        return await list_recording_rules()

    raise HTTPException(status_code=400, detail="No suitable DVR recording engine available")


@router.put("/recording-rules/{rule_id}")
async def update_recording_rule(rule_id: str, payload: RecordingRuleUpdateRequest):
    settings = await _get_hdhomerun_settings_safe()
    set_fields = payload.model_fields_set

    # Check if it's a builtin rule
    rule = await asyncio.to_thread(db.get_recording_rule, rule_id)
    target_provider = payload.server if payload.server in ("builtin", "hdhomerun") else None

    if rule and target_provider == "hdhomerun":
        # Migrate a builtin rule to the official DVR: builtin rows and
        # official-DVR rules live in entirely different places (a local
        # SQLite row vs. a rule owned by the tuner, with its own ID), so
        # "switching providers" means creating an equivalent rule on the
        # target and only removing the original once that succeeds.
        merged_title_match_mode = (
            payload.title_match_mode if "title_match_mode" in set_fields else rule.get("title_match_mode")
        )
        merged_keyword_query = payload.keyword_query if "keyword_query" in set_fields else rule.get("keyword_query")
        is_keyword_rule = bool(merged_keyword_query) or merged_title_match_mode == "contains"
        if is_keyword_rule:
            raise HTTPException(
                status_code=400, detail="Keyword/contains-match rules are only supported by the builtin DVR"
            )

        if not (hdhomerun_client.is_dvr_configured(settings) or hdhomerun_client.is_tuner_configured(settings)):
            raise HTTPException(status_code=400, detail="HDHomeRun DVR is not configured")

        # series_match_key overloads three meanings depending on rule type -
        # see _format_local_rule, which decodes it the same way.
        cur_date_time: int | None = None
        cur_series_id: str | None = None
        series_match_key = rule.get("series_match_key")
        if rule.get("type") == "single" and series_match_key:
            with contextlib.suppress(ValueError, TypeError):
                cur_date_time = int(float(series_match_key))
        elif series_match_key and series_match_key != rule.get("title"):
            cur_series_id = series_match_key

        merged_series_id = payload.series_id if "series_id" in set_fields else cur_series_id
        merged_date_time = payload.date_time if "date_time" in set_fields else cur_date_time
        merged_channel = payload.channel if "channel" in set_fields else rule.get("channel_id")
        merged_recent_only = payload.recent_only if "recent_only" in set_fields else bool(rule.get("new_only"))
        merged_start_padding = (
            payload.start_padding if "start_padding" in set_fields else rule.get("start_padding_seconds")
        )
        merged_end_padding = payload.end_padding if "end_padding" in set_fields else rule.get("end_padding_seconds")
        merged_title = payload.title if "title" in set_fields else rule.get("title")

        series_id = await _resolve_hdhomerun_series_id(merged_series_id, merged_channel, merged_date_time, merged_title)

        # Same free-tier detour as create_recording_rule: a series rule
        # would be silently accepted and never executed on a free account.
        if merged_date_time is None and hdhomerun_client.resolve_account_tier() == "free":
            if not series_id or series_id == "auto":
                raise HTTPException(
                    status_code=400, detail="Could not resolve a SiliconDust SeriesID for this show"
                )
            if rule.get("provider") == "hdhomerun_series_watch":
                await asyncio.to_thread(
                    db.update_recording_rule,
                    rule_id,
                    series_match_key=series_id,
                    channel_id=merged_channel,
                    start_padding_seconds=merged_start_padding or 0,
                    end_padding_seconds=merged_end_padding or 0,
                    new_only=1 if merged_recent_only else 0,
                )
            else:
                await _create_hdhomerun_series_watch_rule(
                    series_id=series_id,
                    channel=merged_channel,
                    recent_only=merged_recent_only,
                    start_padding=merged_start_padding,
                    end_padding=merged_end_padding,
                    title=merged_title,
                )
                await asyncio.to_thread(db.delete_recording_rule, rule_id)
                await asyncio.to_thread(db.delete_scheduled_recordings_for_rule, rule_id)
                run_in_background(expand_rules())
            return await list_recording_rules()

        try:
            await _create_hdhomerun_recording_rule(
                settings,
                series_id=series_id,
                channel=merged_channel,
                date_time=merged_date_time,
                recent_only=merged_recent_only,
                start_padding=merged_start_padding,
                end_padding=merged_end_padding,
            )
        except hdhomerun_client.HDHomeRunError as exc:
            raise HTTPException(status_code=400, detail=f"Could not switch rule to HDHomeRun RECORD: {exc}") from exc

        await asyncio.to_thread(db.delete_recording_rule, rule_id)
        await asyncio.to_thread(db.delete_scheduled_recordings_for_rule, rule_id)
        run_in_background(expand_rules())
        return await list_recording_rules()

    if not rule and target_provider == "builtin":
        # Migrate an official-DVR rule to the builtin engine: create the
        # local row first, then best-effort clean up the tuner-side rule.
        official_rules = await hdhomerun_client.fetch_dvr_recording_rules(settings)
        current = next((r for r in official_rules if r.get("RecordingRuleID") == rule_id), None)
        if current is None:
            raise HTTPException(status_code=404, detail="Recording rule not found")

        merged_series_id = payload.series_id if "series_id" in set_fields else current.get("SeriesID")
        merged_date_time = payload.date_time if "date_time" in set_fields else current.get("DateTimeOnly")
        merged_channel = payload.channel if "channel" in set_fields else current.get("ChannelOnly")
        merged_recent_only = (
            payload.recent_only if "recent_only" in set_fields else bool(current.get("RecentOnly"))
        )
        merged_start_padding = (
            payload.start_padding if "start_padding" in set_fields else current.get("StartPadding")
        )
        merged_end_padding = payload.end_padding if "end_padding" in set_fields else current.get("EndPadding")
        merged_max_episodes_to_keep = (
            payload.max_episodes_to_keep
            if "max_episodes_to_keep" in set_fields
            else current.get("MaxEpisodesToKeep")
        )
        merged_title = payload.title if "title" in set_fields else current.get("Title")

        await _create_builtin_recording_rule(
            series_id=merged_series_id,
            date_time=merged_date_time,
            channel=merged_channel,
            recent_only=merged_recent_only,
            start_padding=merged_start_padding,
            end_padding=merged_end_padding,
            max_episodes_to_keep=merged_max_episodes_to_keep,
            title=merged_title,
            title_match_mode=payload.title_match_mode,
            keyword_query=payload.keyword_query,
            comskip_override=payload.comskip_override,
        )

        try:
            await hdhomerun_client.delete_recording_rule(settings, rule_id)
        except hdhomerun_client.HDHomeRunError as exc:
            # The new builtin rule already exists and works - a stray
            # duplicate left on the official DVR is a lesser problem than
            # reporting failure after the migration actually succeeded.
            logger.warning("Could not delete official DVR rule %s after migrating it to builtin: %s", rule_id, exc)

        return await list_recording_rules()

    if rule:
        update_fields: dict[str, Any] = {}
        if "channel" in set_fields:
            update_fields["channel_id"] = payload.channel or None
        if payload.start_padding is not None:
            update_fields["start_padding_seconds"] = payload.start_padding
        if payload.end_padding is not None:
            update_fields["end_padding_seconds"] = payload.end_padding
        if payload.recent_only is not None:
            update_fields["new_only"] = 1 if payload.recent_only else 0
        if "max_episodes_to_keep" in set_fields:
            update_fields["max_episodes_to_keep"] = payload.max_episodes_to_keep
        if payload.title_match_mode is not None:
            update_fields["title_match_mode"] = (
                payload.title_match_mode if payload.title_match_mode == "contains" else "exact"
            )
        if "keyword_query" in set_fields:
            update_fields["keyword_query"] = payload.keyword_query
        if "comskip_override" in set_fields:
            update_fields["comskip_override"] = (
                payload.comskip_override if payload.comskip_override in ("always", "never") else "default"
            )
        if payload.title is not None:
            update_fields["title"] = payload.title

        if update_fields:
            await asyncio.to_thread(db.update_recording_rule, rule_id, **update_fields)
            await asyncio.to_thread(db.delete_scheduled_recordings_for_rule, rule_id)
            run_in_background(expand_rules())

        return await list_recording_rules()

    # Otherwise forward to official DVR
    try:
        rule_data = payload.model_dump(exclude_unset=True, exclude={"server"})
        await hdhomerun_client.update_recording_rule(settings, rule_id, rule_data)
        return await list_recording_rules()
    except hdhomerun_client.HDHomeRunError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/recording-rules/{rule_id}")
async def delete_recording_rule(rule_id: str):
    settings = await _get_hdhomerun_settings_safe()

    # Check if it's a builtin rule
    rule = await asyncio.to_thread(db.get_recording_rule, rule_id)
    if rule:
        await asyncio.to_thread(db.delete_recording_rule, rule_id)
        await asyncio.to_thread(db.delete_scheduled_recordings_for_rule, rule_id)
        return await list_recording_rules()

    # Otherwise forward to official DVR
    try:
        await hdhomerun_client.delete_recording_rule(settings, rule_id)
    except hdhomerun_client.HDHomeRunError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return await list_recording_rules()
