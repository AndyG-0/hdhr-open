"""TheSportsDB client for looking up team fanart, badges, and league artwork.

Free public tier (API key '3') — no account or authentication required.
Degrades gracefully to None on any network error or timeout.
"""

from __future__ import annotations

import logging
import re
import urllib.parse

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
