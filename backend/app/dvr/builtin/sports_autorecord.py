"""Sports auto-recording: resolves favorited teams' (and, optionally,
currently-ranked or postseason) upcoming games to a local channel via ESPN's
broadcast-network data, and creates one-time builtin DVR recording rules for
them.

Reuses `rule_engine.create_builtin_recording_rule()`'s existing
`type="single"` handling untouched - this module only decides *which* games
to record and *which channel* to point the rule at, the shared
guide-matching engine (app.dvr.builtin.rule_expander) does the rest exactly
as it does for a manually-created single recording.

`recording_rules.channel_id` (despite the column name) stores a channel
*number* string, not a `channels.id` UUID - see `rule_engine.lookup_guide_title`.
The network->channel map (`sports_network_channel_map`) stores the UUID, for
consistency with the existing `xmltv_channel_map`/`sd_station_map`
precedent, so it's resolved to a channel number here immediately before
creating a rule.

A `type="single"` rule still needs a guide-title match to ever actually
record (the epoch window only narrows which programs are considered - see
rule_expander._match_airing). If the guide has no listing yet for a game
days out, `create_builtin_recording_rule` freezes an unmatchable fallback
title (`f"Channel {channel_number}"`); this module retries that resolution
on a later tick (deleting and recreating the rule, since
`recording_rules.title` is otherwise frozen), falling back to a
`title_match_mode="contains"` match against the ESPN matchup title only
once close to air time.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import UTC, datetime
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app import jobs
from app.config import (
    resolve_sports_autorecord_enabled,
    resolve_sports_autorecord_postseason_enabled,
    resolve_sports_autorecord_top25_enabled,
)
from app.dvr.rule_engine import create_builtin_recording_rule
from app.integrations import espn
from app.storage import db

logger = logging.getLogger(__name__)

JOB_ID = "sports_autorecord_sync"
SYNC_INTERVAL_SECONDS = 6 * 3600  # 4x/day: broadcast assignments and flex
# scheduling shift, but not faster than this - avoids hammering ESPN's
# unofficial API.
_TITLE_RESOLUTION_CUTOFF_SECONDS = 24 * 3600  # if the guide still has
# nothing by 24h out, fall back to the ESPN matchup title + "contains".
_POSTSEASON_SEASON_TYPE = 3  # ESPN's season.type for postseason/playoffs.

_RANKED_LEAGUES = ("college-football", "mens-college-basketball")


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def register(scheduler: AsyncIOScheduler) -> None:
    jobs.register_scheduled_job(
        scheduler,
        job_id=JOB_ID,
        name="Sports auto-record sync",
        description="Resolves favorited teams' upcoming games to channels and creates one-time recording rules.",
        func=sync_sports_autorecord,
        trigger="interval",
        seconds=SYNC_INTERVAL_SECONDS,
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )


async def _expand_top25_favorites(existing_favorites: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One synthetic team-shaped favorite per currently AP-Top-25-ranked team
    in each ranked league, skipping teams already explicitly favorited."""
    already_favorited = {(f["league"], f["espn_team_id"]) for f in existing_favorites if f.get("espn_team_id")}
    synthetic: list[dict[str, Any]] = []
    for league in _RANKED_LEAGUES:
        ranked_team_ids = await espn.get_rankings(league)
        if not ranked_team_ids:
            continue
        for team_id in ranked_team_ids:
            if (league, team_id) in already_favorited:
                continue
            synthetic.append(
                {
                    "id": f"top25_{league}_{team_id}",
                    "kind": "top25",
                    "league": league,
                    "espn_team_id": team_id,
                    "team_display_name": None,
                    "enabled": True,
                }
            )
    return synthetic


async def sync_sports_autorecord() -> None:
    if not resolve_sports_autorecord_enabled():
        return

    favorites = [f for f in await asyncio.to_thread(db.list_sports_favorites) if f["enabled"]]
    if resolve_sports_autorecord_top25_enabled():
        favorites += await _expand_top25_favorites(favorites)

    network_map_by_name = {
        row["network_name"]: row["channel_id"] for row in await asyncio.to_thread(db.list_network_channel_map)
    }
    tracked_by_event_id = {row["espn_event_id"]: row for row in await asyncio.to_thread(db.list_tracked_events)}
    postseason_widened = resolve_sports_autorecord_postseason_enabled()

    now = time.time()
    seen_event_ids: set[str] = set()

    for fav in favorites:
        if not fav.get("espn_team_id"):
            continue
        schedule = await espn.get_team_schedule(fav["league"], fav["espn_team_id"])
        if schedule is None:
            continue  # degrade: retry next tick

        for game in schedule:
            if game["start_time"] <= now:
                continue
            is_postseason = game.get("season_type") == _POSTSEASON_SEASON_TYPE
            # A favorited team's own postseason games always record. The
            # postseason toggle only matters for widening scope to
            # non-favorited teams, which this module doesn't do (every game
            # considered here already belongs to an explicitly favorited or
            # top-25 team) - kept as an explicit no-op branch so the intent
            # is visible rather than silently absent.
            if is_postseason and not postseason_widened:
                pass

            seen_event_ids.add(game["event_id"])
            await _sync_one_event(fav, game, network_map_by_name, tracked_by_event_id.get(game["event_id"]))

    # Drop tracking rows for events that fell out of every favorite's
    # schedule window (game passed, or favorite removed) once their rule is
    # already gone. Favorite deletion itself cleans up synchronously (see
    # app.api.sports) - this only mops up events that aged out naturally.
    for event_id, row in tracked_by_event_id.items():
        if event_id in seen_event_ids:
            continue
        if row["recording_rule_id"] and await asyncio.to_thread(db.get_recording_rule, row["recording_rule_id"]):
            continue
        await asyncio.to_thread(db.delete_tracked_event, event_id)


async def _sync_one_event(
    fav: dict[str, Any],
    game: dict[str, Any],
    network_map_by_name: dict[str, str],
    existing: dict[str, Any] | None,
) -> None:
    network = game["broadcast_network"]
    channel_id = network_map_by_name.get(network) if network else None

    if existing is not None:
        if existing["start_ts"] != game["start_time"]:
            # Game rescheduled - drop the stale rule (if any) and fall
            # through to recreate it below.
            if existing["recording_rule_id"]:
                await asyncio.to_thread(db.delete_recording_rule, existing["recording_rule_id"])
                await asyncio.to_thread(db.delete_scheduled_recordings_for_rule, existing["recording_rule_id"])
        elif existing["recording_rule_id"] and existing["title_resolved"]:
            return  # already correctly tracked, nothing to do
        elif existing["recording_rule_id"] and not existing["title_resolved"]:
            if game["start_time"] - time.time() > _TITLE_RESOLUTION_CUTOFF_SECONDS:
                return  # not yet worth retrying
            await asyncio.to_thread(db.delete_recording_rule, existing["recording_rule_id"])
            await asyncio.to_thread(db.delete_scheduled_recordings_for_rule, existing["recording_rule_id"])

    if channel_id is None:
        if network:  # surface as unresolved only if there's a network to map
            await asyncio.to_thread(
                db.upsert_tracked_event,
                {
                    "espn_event_id": game["event_id"],
                    "favorite_id": fav["id"],
                    "recording_rule_id": None,
                    "league": fav["league"],
                    "start_ts": game["start_time"],
                    "network_name": network,
                    "title_resolved": False,
                    "updated_at": _now_iso(),
                },
            )
        return

    channel_row = await asyncio.to_thread(db.get_channel, channel_id)
    if channel_row is None:
        logger.warning("sports_autorecord: mapped channel_id %r no longer exists, skipping", channel_id)
        return
    channel_number = channel_row["channel_number"]  # critical: pass the NUMBER, not the UUID - see module docstring

    near_air = game["start_time"] - time.time() <= _TITLE_RESOLUTION_CUTOFF_SECONDS
    rule = await create_builtin_recording_rule(
        series_id=None,
        date_time=int(game["start_time"]),
        channel=channel_number,
        recent_only=False,
        start_padding=0,
        end_padding=900,
        max_episodes_to_keep=None,
        title=game["matchup_title"] if near_air else None,
        title_match_mode="contains" if near_air else None,
        keyword_query=None,
        fallback_reason="sports_autorecord",
    )
    title_resolved = rule["title"] != f"Channel {channel_number}"
    await asyncio.to_thread(
        db.upsert_tracked_event,
        {
            "espn_event_id": game["event_id"],
            "favorite_id": fav["id"],
            "recording_rule_id": rule["id"],
            "league": fav["league"],
            "start_ts": game["start_time"],
            "network_name": network,
            "title_resolved": title_resolved,
            "updated_at": _now_iso(),
        },
    )
