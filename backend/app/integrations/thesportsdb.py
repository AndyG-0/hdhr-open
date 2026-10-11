"""TheSportsDB client for looking up team fanart, badges, and league artwork.

Free public tier (API key '3') — no account or authentication required.
Degrades gracefully to None on any network error or timeout.
"""

from __future__ import annotations

import logging
import re
import urllib.parse
from datetime import date, datetime
from typing import Any

import httpx

logger = logging.getLogger(__name__)

API_BASE_URL = "https://www.thesportsdb.com/api/v1/json/3"
_TIMEOUT_SECONDS = 5.0

# Predefined high-resolution league badges / logos for fast, reliable lookup
LEAGUE_LOGOS: dict[str, str] = {
    "nfl": "https://r2.thesportsdb.com/images/media/league/badge/71542f1784717145.png",
    "nba": "https://r2.thesportsdb.com/images/media/league/badge/s4whha1784717523.png",
    "mlb": "https://r2.thesportsdb.com/images/media/league/badge/4v70d91784717757.png",
    "nhl": "https://r2.thesportsdb.com/images/media/league/badge/p3hvd51784717904.png",
    "mls": "https://r2.thesportsdb.com/images/media/league/badge/uqwrwt1421434948.png",
    "pga": "https://r2.thesportsdb.com/images/media/league/badge/vwwtxv1434479522.png",
    "nascar": "https://r2.thesportsdb.com/images/media/league/badge/uqxrqx1434478440.png",
    "premier league": "https://r2.thesportsdb.com/images/media/league/badge/q630rf1784764126.png",
    "champions league": "https://r2.thesportsdb.com/images/media/league/badge/03f0b21784764835.png",
    "formula 1": "https://r2.thesportsdb.com/images/media/league/badge/yutvtr1421865306.png",
    "f1": "https://r2.thesportsdb.com/images/media/league/badge/yutvtr1421865306.png",
    "ufc": "https://r2.thesportsdb.com/images/media/league/badge/25h47s1547043818.png",
    "wwe": "https://r2.thesportsdb.com/images/media/league/badge/vqyuyr1434478796.png",
    "college football": "https://r2.thesportsdb.com/images/media/league/badge/71542f1784717145.png",
    "ncaa football": "https://r2.thesportsdb.com/images/media/league/badge/71542f1784717145.png",
}

# In-memory cache for search results so repeated queries for the same team/league don't hit the API
_sports_cache: dict[str, str | None] = {}


def extract_matchup_teams(text: str) -> list[str]:
    """Extract candidate team names from a matchup title or episode title.

    Handles formats like:
      - 'Dallas Cowboys at Arizona Cardinals'
      - 'Arsenal vs Chelsea'
      - 'Lakers vs. Warriors'
      - 'Team A @ Team B'
    """
    if not text:
        return []
    for sep in (" at ", " vs. ", " vs ", " @ ", " - "):
        if sep in text:
            parts = [p.strip() for p in text.split(sep) if p.strip()]
            cleaned = []
            for p in parts:
                # Remove rank prefixes like '#1 ', 'No. 5 '
                c = re.sub(r"^(No\.\s*\d+|#\d+)\s*", "", p)
                if c:
                    cleaned.append(c)
            return cleaned
    return [text.strip()] if text.strip() else []


async def search_sports_poster(title: str, episode_title: str | None = None) -> str | None:
    """Search for team artwork or league logos for a sports event."""
    cache_key = f"{title.lower()}|{(episode_title or '').lower()}"
    if cache_key in _sports_cache:
        return _sports_cache[cache_key]

    t_lower = (title or "").lower()

    # 1. Try extracting teams from episode_title if it has a matchup pattern
    candidate_teams = extract_matchup_teams(episode_title or "")
    if candidate_teams:
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
                for team_name in candidate_teams:
                    url = f"{API_BASE_URL}/searchteams.php?t={urllib.parse.quote(team_name)}"
                    try:
                        resp = await client.get(url)
                        if resp.status_code == 200:
                            data = resp.json()
                            teams = data.get("teams")
                            if teams and isinstance(teams, list) and len(teams) > 0:
                                t = teams[0]
                                poster = t.get("strFanart1") or t.get("strBadge") or t.get("strBanner")
                                if poster:
                                    _sports_cache[cache_key] = poster
                                    return poster
                    except Exception:
                        pass
        except Exception:
            pass

    # 2. Check predefined league badges from title
    for league_key, logo_url in LEAGUE_LOGOS.items():
        if re.search(r"\b" + re.escape(league_key) + r"\b", t_lower):
            _sports_cache[cache_key] = logo_url
            return logo_url

    # 3. Try team lookup on the title itself
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            url = f"{API_BASE_URL}/searchteams.php?t={urllib.parse.quote(title)}"
            resp = await client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                teams = data.get("teams")
                if teams and isinstance(teams, list) and len(teams) > 0:
                    t = teams[0]
                    poster = t.get("strFanart1") or t.get("strBadge") or t.get("strBanner")
                    if poster:
                        _sports_cache[cache_key] = poster
                        return poster
    except Exception:
        pass

    _sports_cache[cache_key] = None
    return None


_FINISHED_STATUSES = {"MATCH FINISHED", "FINISHED", "FT", "AOT", "AET"}
_SCHEDULED_STATUSES = {"NS"}


_EVENT_DATE_TOLERANCE_DAYS = 1


async def _find_event(team_a: str, team_b: str, event_date: date | None = None) -> dict[str, Any] | None:
    """Find the TheSportsDB event dict for a matchup between two teams, or `None`.

    Tries both name orderings ("A vs B" and "B vs A") since broadcast titles
    don't reliably put the home team first. A rivalry between the same two
    teams recurs every season, and which ordering returns results can vary
    by year (home/away alternates), so both orderings are always searched
    and their results pooled rather than stopping at the first non-empty one
    - otherwise a season's game can be missed entirely because the *other*
    year's game matched first.

    When `event_date` is given, only a candidate within
    `_EVENT_DATE_TOLERANCE_DAYS` of it is returned - a wrong-year score is
    worse than no score, so an unconfirmed match yields `None` instead of
    silently falling back to an unrelated past meeting. Without an
    `event_date` there's nothing to disambiguate with, so the first result
    found is returned as before.
    """
    candidates: list[dict[str, Any]] = []
    for first, second in ((team_a, team_b), (team_b, team_a)):
        query = f"{first}_vs_{second}".replace(" ", "_")
        url = f"{API_BASE_URL}/searchevents.php?e={urllib.parse.quote(query)}"
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
                resp = await client.get(url)
            if resp.status_code != 200:
                continue
            data = resp.json()
        except Exception:
            continue

        events = data.get("event")
        if not events or not isinstance(events, list):
            continue

        if event_date is None:
            return events[0]

        candidates.extend(events)

    if not candidates:
        return None
    assert event_date is not None  # candidates is only populated on the event_date-given path above

    best_event = None
    best_delta = None
    for candidate in candidates:
        raw_date = candidate.get("dateEvent")
        if not raw_date:
            continue
        try:
            parsed = datetime.strptime(raw_date, "%Y-%m-%d").date()
        except ValueError:
            continue
        delta = abs((parsed - event_date).days)
        if best_delta is None or delta < best_delta:
            best_event, best_delta = candidate, delta

    if best_event is not None and best_delta is not None and best_delta <= _EVENT_DATE_TOLERANCE_DAYS:
        return best_event

    return None


def _status_from_event(event: dict[str, Any]) -> str | None:
    status = (event.get("strStatus") or "").strip()
    if not status:
        return None
    status_upper = status.upper()
    if status_upper in _FINISHED_STATUSES:
        return "finished"
    if status_upper in _SCHEDULED_STATUSES:
        return "scheduled"
    return "live"


async def get_event_status(team_a: str, team_b: str, event_date: date | None = None) -> str | None:
    """Best-effort live status lookup for a matchup between two teams.

    Returns "scheduled", "live", or "finished", or None if the event can't be
    confidently identified. Deliberately not cached (unlike poster art) since
    status changes over the lifetime of a broadcast and a stale cached value
    could permanently hide a "finished" or "live" transition.
    """
    event = await _find_event(team_a, team_b, event_date)
    if event is None:
        return None
    return _status_from_event(event)


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


async def get_event_details(team_a: str, team_b: str, event_date: date | None = None) -> dict[str, Any] | None:
    """Fuller best-effort event data for Insights: status + score + venue +
    teams, or `None` if no matchup could be identified.

    Deliberately never cached, for the same reason as `get_event_status`: a
    cached "finished" status or stale score would be wrong the next time the
    modal opens mid-broadcast.

    The free TheSportsDB tier doesn't push in-progress scores in real time -
    its event record for a live game can lag the actual broadcast by many
    minutes, which is worse than showing nothing (a wrong "live" score reads
    as more authoritative than it is). So while `status == "live"`, scores
    are deliberately omitted; a `"finished"` score is a stable fact by the
    time it's reported and is shown as-is.
    """
    event = await _find_event(team_a, team_b, event_date)
    if event is None:
        return None
    status = _status_from_event(event)
    home_score = _int_or_none(event.get("intHomeScore"))
    away_score = _int_or_none(event.get("intAwayScore"))
    if status == "live":
        home_score = None
        away_score = None
    return {
        "status": status,
        "home_team": event.get("strHomeTeam"),
        "away_team": event.get("strAwayTeam"),
        "home_score": home_score,
        "away_score": away_score,
        "venue": event.get("strVenue"),
        "league": event.get("strLeague"),
        "date_event": event.get("dateEvent"),
        "time": event.get("strTime"),
    }
