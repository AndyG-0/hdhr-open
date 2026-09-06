"""Read-only guide tools: search, now/next, program details, and the
channel lineup with live tuner availability.

Built directly on `db.list_channels`/`db.list_guide_programs`/
`db.resolve_guide_programs` and `tuner_allocator`, deliberately *not* on
`app.api.guide`'s `get_channels()` — that route does a live, exception-
raising tuner HTTP call (404s when no tuner is configured), and a tool must
never raise. `_row_to_airing` is imported from `app.api.guide` since it's
stable, private shaping logic already used by three other guide/dvr call
sites — duplicating it here would be worse than the minor layering smell.
"""

from __future__ import annotations

import asyncio
import re
import time
from typing import Any

from app.ai.tools.registry import ToolDefinition, register
from app.api.guide import _row_to_airing
from app.config import resolve_guide_provider_priority
from app.dvr.builtin.tuner_allocator import tuner_allocator
from app.storage import db

_SEARCH_WINDOW_PAST_SECONDS = 3600
_SEARCH_WINDOW_FUTURE_SECONDS = 14 * 86400
_NOW_PLAYING_WINDOW_FUTURE_SECONDS = 3 * 3600
_DEFAULT_SEARCH_LIMIT = 20

# Splits a compound/paraphrased query like "Alabama vs Georgia and Ohio
# State at Michigan" into meaningful chunks ("alabama", "georgia", "ohio
# state", "michigan"). Used as a fallback when the model re-derives a search
# query from its own earlier prose (e.g. after losing track of the original
# structured results) and combines multiple matchups into one query that
# would otherwise never substring-match any single guide entry.
_QUERY_SPLIT_RE = re.compile(r"\b(?:vs\.?|at|and)\b|[,&]", re.IGNORECASE)
_MIN_FALLBACK_TOKEN_LENGTH = 3


def _query_tokens(query: str) -> list[str]:
    return [chunk.strip() for chunk in _QUERY_SPLIT_RE.split(query) if chunk.strip()]


async def get_hdhomerun_settings_or_empty() -> dict[str, Any]:
    """Like `app.api._hdhomerun_settings.get_hdhomerun_settings`, but never
    raises — returns `{}` (treated as "not configured" by every
    `tuner_allocator`/`hdhomerun_client` call) instead of a 404, since a
    tool must never raise for something as ordinary as "no tuner yet"."""
    row = await asyncio.to_thread(db.get_network_integration, "hdhomerun")
    return row["settings"] if row else {}


async def _channels_and_resolved_airings(
    start_ts: float, end_ts: float
) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    channels = await asyncio.to_thread(db.list_channels, False)
    channel_ids = [c["id"] for c in channels]
    rows = await asyncio.to_thread(db.list_guide_programs, channel_ids, start_ts, end_ts)
    priority = resolve_guide_provider_priority()
    resolved = db.resolve_guide_programs(channels, rows, priority)
    return channels, resolved


async def search_guide(query: str, limit: int = _DEFAULT_SEARCH_LIMIT) -> dict[str, Any]:
    """Search upcoming (and just-aired) guide listings by title/synopsis
    substring match, case-insensitive. Falls back to matching individual
    tokens of a compound query (e.g. several team names combined into one
    string) when the whole query isn't a substring of anything — see
    `_query_tokens`."""
    now = time.time()
    channels, resolved = await _channels_and_resolved_airings(
        now - _SEARCH_WINDOW_PAST_SECONDS, now + _SEARCH_WINDOW_FUTURE_SECONDS
    )
    channels_by_id = {c["id"]: c for c in channels}
    query_lower = query.strip().lower()
    tokens = _query_tokens(query_lower)

    matches: list[dict[str, Any]] = []
    for channel_id, rows in resolved.items():
        channel = channels_by_id[channel_id]
        for row in rows:
            title = (row.get("title") or "").lower()
            synopsis = (row.get("synopsis") or "").lower()
            haystack = f"{title} {synopsis}"
            hit = query_lower in haystack
            if not hit and len(tokens) > 1:
                hit = any(token in haystack for token in tokens if len(token) >= _MIN_FALLBACK_TOKEN_LENGTH)
            if hit:
                matches.append(_row_to_airing(row, channel["channel_number"]))

    matches.sort(key=lambda a: a["start"])
    return {"results": matches[: max(1, limit)], "total_matches": len(matches)}


async def get_now_playing(channel_number: str | None = None) -> dict[str, Any]:
    """What's currently airing (and up next) on one channel, or all
    channels when `channel_number` is omitted."""
    now = time.time()
    channels, resolved = await _channels_and_resolved_airings(now, now + _NOW_PLAYING_WINDOW_FUTURE_SECONDS)
    if channel_number:
        channels = [c for c in channels if c["channel_number"] == channel_number]
        if not channels:
            return {"error": f"No channel numbered '{channel_number}'"}

    results = []
    for channel in channels:
        rows = resolved.get(channel["id"], [])
        current = next_up = None
        for row in rows:
            if row["start_ts"] <= now < row["end_ts"]:
                current = _row_to_airing(row, channel["channel_number"])
            elif row["start_ts"] > now and next_up is None:
                next_up = _row_to_airing(row, channel["channel_number"])
        results.append(
            {
                "channel_number": channel["channel_number"],
                "channel_name": channel["name"],
                "now": current,
                "next": next_up,
            }
        )
    return {"channels": results}


async def get_program_details(channel_number: str, start: float) -> dict[str, Any]:
    """Full details for one specific airing, identified by the channel and
    its guide `start` timestamp (as returned by `search_guide`/
    `get_now_playing`)."""
    channel = await asyncio.to_thread(db.get_channel_by_number, channel_number)
    if channel is None:
        return {"error": f"No channel numbered '{channel_number}'"}

    rows = await asyncio.to_thread(db.list_guide_programs, [channel["id"]], start - 60, start + 60)
    priority = resolve_guide_provider_priority()
    resolved = db.resolve_guide_programs([channel], rows, priority)
    for row in resolved.get(channel["id"], []):
        if abs(row["start_ts"] - start) < 60:
            return _row_to_airing(row, channel_number)
    return {"error": "No airing found on that channel at that time"}


async def get_channel_lineup() -> dict[str, Any]:
    """The household's channel lineup plus live tuner availability — how
    many tuners exist and how many are currently free, so the assistant can
    tell whether a new recording would actually be able to start."""
    channels = await asyncio.to_thread(db.list_channels, False)
    settings = await get_hdhomerun_settings_or_empty()
    tuner_count = await tuner_allocator.get_tuner_count(settings)
    in_use_count = await tuner_allocator.get_hardware_in_use_count(settings)
    return {
        "channels": [
            {"channel_number": c["channel_number"], "name": c["name"], "is_hd": bool(c.get("is_hd", 0))}
            for c in channels
        ],
        "tuner_count": tuner_count,
        "tuners_in_use": in_use_count,
        "tuners_available": max(0, tuner_count - in_use_count),
    }


register(
    ToolDefinition(
        name="search_guide",
        description="Search TV guide listings (upcoming and recently-aired) by title or synopsis substring match.",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Text to search for in program titles/synopses."},
                "limit": {"type": "integer", "description": "Max results to return.", "default": 20},
            },
            "required": ["query"],
        },
        handler=search_guide,
    )
)

register(
    ToolDefinition(
        name="get_now_playing",
        description="What's currently airing (and up next) on one channel, or every channel if none is given.",
        parameters={
            "type": "object",
            "properties": {
                "channel_number": {
                    "type": "string",
                    "description": "A specific channel number, or omit for all channels.",
                },
            },
        },
        handler=get_now_playing,
    )
)

register(
    ToolDefinition(
        name="get_program_details",
        description=(
            "Full details for one specific airing, identified by channel number and its guide "
            "start timestamp (unix seconds) from a prior search_guide/get_now_playing result."
        ),
        parameters={
            "type": "object",
            "properties": {
                "channel_number": {"type": "string"},
                "start": {"type": "number", "description": "The airing's start time, unix seconds."},
            },
            "required": ["channel_number", "start"],
        },
        handler=get_program_details,
    )
)

register(
    ToolDefinition(
        name="get_channel_lineup",
        description="The household's channel lineup, plus how many tuners exist and how many are currently free.",
        parameters={"type": "object", "properties": {}},
        handler=get_channel_lineup,
    )
)
