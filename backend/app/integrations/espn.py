"""ESPN client for favorited-team schedules, league rosters, and rankings.

Uses ESPN's unofficial "site API" (`site.api.espn.com/apis/site/v2/sports/...`)
- no API key, undocumented, can change or break without notice. Degrades
gracefully to None on any network error or unexpected response shape, same
philosophy as app.integrations.thesportsdb.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any

import httpx

logger = logging.getLogger(__name__)

API_BASE_URL = "https://site.api.espn.com/apis/site/v2/sports"
_TIMEOUT_SECONDS = 5.0
_TEAMS_CACHE_TTL_SECONDS = 24 * 3600  # rosters/league membership rarely change intra-season

LEAGUE_SLUGS: dict[str, str] = {
    "nfl": "football/nfl",
    "college-football": "football/college-football",
    "nba": "basketball/nba",
    "mlb": "baseball/mlb",
    "nhl": "hockey/nhl",
    "mens-college-basketball": "basketball/mens-college-basketball",
    "eng.1": "soccer/eng.1",
    "esp.1": "soccer/esp.1",
    "usa.1": "soccer/usa.1",
    "uefa.champions": "soccer/uefa.champions",
}

# league -> (fetched_at, teams)
_teams_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}


async def list_league_teams(league: str) -> list[dict[str, Any]] | None:
    """All teams in `league` as [{"id", "display_name", "abbreviation", "logo_url"}].

    In-process cached with a long TTL since league membership rarely changes
    intra-season. Returns None on any failure (unknown league, network
    error, unexpected response shape) rather than raising.
    """
    slug = LEAGUE_SLUGS.get(league)
    if slug is None:
        return None

    cached = _teams_cache.get(league)
    if cached is not None and time.time() - cached[0] < _TEAMS_CACHE_TTL_SECONDS:
        return cached[1]

    url = f"{API_BASE_URL}/{slug}/teams"
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            resp = await client.get(url, params={"limit": 200})
        if resp.status_code != 200:
            return None
        data = resp.json()
    except Exception:
        logger.debug("espn.list_league_teams(%s) failed", league, exc_info=True)
        return None

    teams: list[dict[str, Any]] = []
    try:
        entries = data["sports"][0]["leagues"][0]["teams"]
        for entry in entries:
            team = entry.get("team") or {}
            if not team.get("id"):
                continue
            logos = team.get("logos") or []
            teams.append(
                {
                    "id": str(team["id"]),
                    "display_name": team.get("displayName") or team.get("name") or "",
                    "abbreviation": team.get("abbreviation"),
                    "logo_url": logos[0].get("href") if logos else None,
                }
            )
    except (KeyError, IndexError, TypeError):
        logger.debug("espn.list_league_teams(%s) got unexpected response shape", league, exc_info=True)
        return None

    _teams_cache[league] = (time.time(), teams)
    return teams


async def get_team_schedule(league: str, team_id: str) -> list[dict[str, Any]] | None:
    """`team_id`'s upcoming (and recent) games as [{"event_id", "start_time"
    (epoch seconds), "broadcast_network" (str|None), "season_type" (int),
    "matchup_title"}].

    Deliberately NOT cached - broadcast network assignments and flex
    scheduling shift, so this is fetched fresh every sync tick.
    """
    slug = LEAGUE_SLUGS.get(league)
    if slug is None:
        return None

    url = f"{API_BASE_URL}/{slug}/teams/{team_id}/schedule"
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            resp = await client.get(url)
        if resp.status_code != 200:
            return None
        data = resp.json()
    except Exception:
        logger.debug("espn.get_team_schedule(%s, %s) failed", league, team_id, exc_info=True)
        return None

    games: list[dict[str, Any]] = []
    try:
        for event in data.get("events") or []:
            competitions = event.get("competitions") or []
            if not competitions:
                continue
            competition = competitions[0]
            date_str = event.get("date") or competition.get("date")
            if not date_str:
                continue
            try:
                start_time = datetime.fromisoformat(date_str.replace("Z", "+00:00")).timestamp()
            except ValueError:
                continue

            broadcast_network = None
            broadcasts = competition.get("broadcasts") or []
            if broadcasts:
                broadcast_network = (broadcasts[0].get("media") or {}).get("shortName")

            season_type = ((event.get("seasonType") or {}).get("type")) or ((data.get("season") or {}).get("type"))

            games.append(
                {
                    "event_id": str(event.get("id") or competition.get("id") or ""),
                    "start_time": start_time,
                    "broadcast_network": broadcast_network,
                    "season_type": season_type if isinstance(season_type, int) else None,
                    "matchup_title": event.get("name") or event.get("shortName") or "",
                }
            )
    except (KeyError, TypeError):
        logger.debug("espn.get_team_schedule(%s, %s) got unexpected response shape", league, team_id, exc_info=True)
        return None

    return [g for g in games if g["event_id"]]


async def get_rankings(league: str, poll: str = "ap") -> list[str] | None:
    """Ordered ESPN team ids in the current Top 25 for `league`.

    Only meaningful for "college-football" / "mens-college-basketball".
    Returns None on any failure.
    """
    slug = LEAGUE_SLUGS.get(league)
    if slug is None:
        return None

    url = f"{API_BASE_URL}/{slug}/rankings"
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            resp = await client.get(url)
        if resp.status_code != 200:
            return None
        data = resp.json()
    except Exception:
        logger.debug("espn.get_rankings(%s, %s) failed", league, poll, exc_info=True)
        return None

    try:
        rankings = data.get("rankings") or []
        chosen = None
        for entry in rankings:
            name = (entry.get("name") or entry.get("shortName") or "").lower()
            if poll.lower() in name:
                chosen = entry
                break
        if chosen is None and rankings:
            chosen = rankings[0]
        if chosen is None:
            return None
        team_ids = []
        for rank_entry in chosen.get("ranks") or []:
            team = rank_entry.get("team") or {}
            if team.get("id"):
                team_ids.append(str(team["id"]))
        return team_ids
    except (KeyError, TypeError):
        logger.debug("espn.get_rankings(%s, %s) got unexpected response shape", league, poll, exc_info=True)
        return None
