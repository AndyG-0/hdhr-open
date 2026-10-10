"""DVR recording rules (create/list/update/delete), for both the builtin and
official HDHomeRun DVR engines. Mounted into dvr.py's router via
include_router, so it inherits that router's prefix/auth dependency.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field

from app.api._dvr_shared import _get_hdhomerun_settings_safe
from app.async_utils import run_in_background
from app.config import resolve_dvr_server_priority
from app.dvr import rule_engine
from app.dvr.builtin.rule_expander import expand_rules
from app.dvr.rule_engine import (
    create_builtin_recording_rule as _create_builtin_recording_rule,
)
from app.dvr.rule_engine import (
    create_hdhomerun_recording_rule as _create_hdhomerun_recording_rule,
)
from app.dvr.rule_engine import (
    create_hdhomerun_series_watch_rule as _create_hdhomerun_series_watch_rule,
)
from app.dvr.rule_engine import (
    lookup_guide_title as _lookup_guide_title,
)
from app.dvr.rule_engine import (
    lookup_hdhomerun_series_id as _lookup_hdhomerun_series_id,
)
from app.dvr.rule_engine import (
    reconcile_hdhomerun_fallback_rules,
)
from app.dvr.rule_engine import (
    resolve_hdhomerun_series_id as _resolve_hdhomerun_series_id,
)
from app.integrations import hdhomerun_client
from app.storage import db

# _lookup_guide_title/_lookup_hdhomerun_series_id/reconcile_hdhomerun_fallback_rules
# are re-exported here (unused in this file otherwise) for app.ai.tools.recording
# and existing tests, which reach them as module attributes of dvr_rules - the
# actual dual-engine fallback/migration logic now lives in app.dvr.rule_engine
# so the route handlers below stay thin wrappers around it.
__all__ = [
    "router",
    "reconcile_hdhomerun_fallback_rules",
    "_lookup_guide_title",
    "_lookup_hdhomerun_series_id",
]

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



@router.post("/recording-rules")
async def create_recording_rule(
    payload: RecordingRuleCreateRequest,
    response: Response = None,  # type: ignore[assignment]  # FastAPI injects a real Response when
    # routed normally; the default lets app.ai.tools.recording call this directly as a plain function.
):
    settings = await _get_hdhomerun_settings_safe()
    priority = resolve_dvr_server_priority()
    fallback_reason = await rule_engine.create_rule_with_fallback(payload, settings, priority)
    if fallback_reason and response is not None:
        response.headers["X-DVR-Fallback"] = "true"
        response.headers["X-DVR-Fallback-Reason"] = fallback_reason
    return await list_recording_rules()


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
