"""Recording tools: browsing existing rules/recordings, and scheduling/
cancelling — the latter as preview+execute pairs so nothing actually
mutates the DVR until a human confirms (see `app.ai.tools.registry`).

Every tool here (read and write) is gated behind `enable_recording_tools` —
a single settings checkbox controls the whole DVR tool surface, so the
model either has full guide+DVR read access plus propose-only write access,
or none of it at all.

Wraps `app.api.dvr`'s route handlers directly rather than duplicating their
dual-engine (builtin/HDHomeRun) logic — they're plain importable async
functions with no FastAPI `Depends` parameters, since dvr.py enforces auth
at the router level, not per-function.
"""

from __future__ import annotations

import asyncio
from typing import Any

from app.ai.tools.guide import get_hdhomerun_settings_or_empty
from app.ai.tools.registry import ToolDefinition, register
from app.api import dvr as dvr_api
from app.dvr.builtin.tuner_allocator import tuner_allocator
from app.storage import db

_PERMISSION = "enable_recording_tools"


# --- read-only ----------------------------------------------------------------


async def list_recording_rules() -> dict[str, Any]:
    rules = await dvr_api.list_recording_rules()
    return {"rules": rules}


async def list_recordings() -> dict[str, Any]:
    recordings = await dvr_api.list_recordings()
    return {"recordings": recordings}


async def check_recording_conflicts(channel_number: str) -> dict[str, Any]:
    """Whether a new recording on `channel_number` right now would actually
    get a free hardware tuner."""
    settings = await get_hdhomerun_settings_or_empty()
    available = await tuner_allocator.is_tuner_available(settings, channel_number=channel_number)
    tuner_count = await tuner_allocator.get_tuner_count(settings)
    in_use_count = await tuner_allocator.get_hardware_in_use_count(settings)
    return {
        "channel_number": channel_number,
        "tuner_available": available,
        "tuner_count": tuner_count,
        "tuners_in_use": in_use_count,
    }


# --- schedule_recording (mutating) ---------------------------------------------


def _describe_schedule_kind(
    *, date_time: int | None, recent_only: bool | None, keyword_query: str | None, title_match_mode: str | None
) -> str:
    if date_time:
        return "single airing"
    if keyword_query or title_match_mode == "contains":
        return "keyword/contains match"
    return "series (new episodes only)" if recent_only else "series (all episodes)"


async def _preview_schedule_recording(
    *,
    series_id: str | None = None,
    channel: str | None = None,
    date_time: int | None = None,
    recent_only: bool | None = None,
    start_padding: int | None = None,
    end_padding: int | None = None,
    max_episodes_to_keep: int | None = None,
    server: str | None = None,
    title: str | None = None,
    title_match_mode: str | None = None,
    keyword_query: str | None = None,
) -> dict[str, Any]:
    resolved_title = title or await asyncio.to_thread(dvr_api._lookup_guide_title, series_id, channel, date_time)
    channel_row = await asyncio.to_thread(db.get_channel_by_number, channel) if channel else None
    return {
        "title": resolved_title,
        "channel": channel,
        "channel_name": channel_row["name"] if channel_row else None,
        "date_time": date_time,
        "kind": _describe_schedule_kind(
            date_time=date_time, recent_only=recent_only, keyword_query=keyword_query, title_match_mode=title_match_mode
        ),
        "recent_only": bool(recent_only),
        "start_padding_seconds": start_padding or 0,
        "end_padding_seconds": end_padding or 0,
        "max_episodes_to_keep": max_episodes_to_keep,
        "keyword_query": keyword_query,
    }


async def _execute_schedule_recording(
    *,
    series_id: str | None = None,
    channel: str | None = None,
    date_time: int | None = None,
    recent_only: bool | None = None,
    start_padding: int | None = None,
    end_padding: int | None = None,
    max_episodes_to_keep: int | None = None,
    server: str | None = None,
    title: str | None = None,
    title_match_mode: str | None = None,
    keyword_query: str | None = None,
) -> dict[str, Any]:
    payload = dvr_api.RecordingRuleCreateRequest(
        series_id=series_id,
        channel=channel,
        date_time=date_time,
        recent_only=recent_only,
        start_padding=start_padding,
        end_padding=end_padding,
        max_episodes_to_keep=max_episodes_to_keep,
        server=server,
        title=title,
        title_match_mode=title_match_mode,
        keyword_query=keyword_query,
    )
    rules = await dvr_api.create_recording_rule(payload)
    return {"status": "scheduled", "rules": rules}


# --- cancel_recording_rule (mutating) -------------------------------------------


async def _preview_cancel_recording_rule(rule_id: str) -> dict[str, Any]:
    builtin = await asyncio.to_thread(db.get_recording_rule, rule_id)
    if builtin:
        return {"rule_id": rule_id, "title": builtin.get("title"), "provider": "builtin"}
    rules = await dvr_api.list_recording_rules()
    match = next((r for r in rules if r.get("RecordingRuleID") == rule_id), None)
    if match is None:
        return {"error": f"No recording rule with id '{rule_id}'"}
    return {"rule_id": rule_id, "title": match.get("Title"), "provider": match.get("provider", "hdhomerun")}


async def _execute_cancel_recording_rule(rule_id: str) -> dict[str, Any]:
    rules = await dvr_api.delete_recording_rule(rule_id)
    return {"status": "cancelled", "rules": rules}


# --- delete_recording (mutating) ------------------------------------------------


async def _preview_delete_recording(recording_id: str) -> dict[str, Any]:
    recording = await asyncio.to_thread(db.get_recording, recording_id)
    if recording is None:
        return {"error": f"No recording with id '{recording_id}'"}
    return {
        "recording_id": recording_id,
        "title": recording.get("title"),
        "episode_title": recording.get("episode_title"),
    }


async def _execute_delete_recording(recording_id: str) -> dict[str, Any]:
    result = await dvr_api.delete_recording(recording_id)
    return dict(result)


# --- registration ----------------------------------------------------------------

register(
    ToolDefinition(
        name="list_recording_rules",
        description="List all active recording rules (builtin and, if configured, official HDHomeRun DVR).",
        parameters={"type": "object", "properties": {}},
        handler=list_recording_rules,
        requires_permission=_PERMISSION,
    )
)

register(
    ToolDefinition(
        name="list_recordings",
        description="List completed/in-progress recordings in the DVR library.",
        parameters={"type": "object", "properties": {}},
        handler=list_recordings,
        requires_permission=_PERMISSION,
    )
)

register(
    ToolDefinition(
        name="check_recording_conflicts",
        description="Check whether a given channel currently has a free hardware tuner available for a new recording.",
        parameters={
            "type": "object",
            "properties": {"channel_number": {"type": "string"}},
            "required": ["channel_number"],
        },
        handler=check_recording_conflicts,
        requires_permission=_PERMISSION,
    )
)

register(
    ToolDefinition(
        name="schedule_recording",
        description=(
            "Propose scheduling a recording (a single airing, or a recurring series/keyword rule). "
            "This only proposes the action for the user to confirm — it never schedules anything by itself."
        ),
        parameters={
            "type": "object",
            "properties": {
                "series_id": {"type": "string", "description": "Guide series id, if known, for a series rule."},
                "channel": {"type": "string", "description": "Channel number to record on."},
                "date_time": {
                    "type": "integer",
                    "description": (
                        "Unix timestamp of a specific airing's start, for a single (non-recurring) recording."
                    ),
                },
                "recent_only": {
                    "type": "boolean",
                    "description": "For series rules: only record new (non-repeat) episodes.",
                },
                "start_padding": {"type": "integer", "description": "Seconds to start early."},
                "end_padding": {"type": "integer", "description": "Seconds to end late."},
                "max_episodes_to_keep": {"type": "integer", "minimum": 1},
                "title": {"type": "string", "description": "Explicit title, if not resolvable from the guide."},
                "title_match_mode": {"type": "string", "enum": ["exact", "contains"]},
                "keyword_query": {
                    "type": "string",
                    "description": "Keyword filter checked against episode synopsis/category.",
                },
            },
        },
        mutating=True,
        preview=_preview_schedule_recording,
        execute=_execute_schedule_recording,
        requires_permission=_PERMISSION,
    )
)

register(
    ToolDefinition(
        name="cancel_recording_rule",
        description=(
            "Propose cancelling a recording rule. This only proposes the action for the user to confirm — "
            "it never cancels anything by itself."
        ),
        parameters={
            "type": "object",
            "properties": {"rule_id": {"type": "string"}},
            "required": ["rule_id"],
        },
        mutating=True,
        preview=_preview_cancel_recording_rule,
        execute=_execute_cancel_recording_rule,
        requires_permission=_PERMISSION,
    )
)

register(
    ToolDefinition(
        name="delete_recording",
        description=(
            "Propose deleting a completed recording from the library. This only proposes the action for the "
            "user to confirm — it never deletes anything by itself."
        ),
        parameters={
            "type": "object",
            "properties": {"recording_id": {"type": "string"}},
            "required": ["recording_id"],
        },
        mutating=True,
        preview=_preview_delete_recording,
        execute=_execute_delete_recording,
        requires_permission=_PERMISSION,
    )
)
