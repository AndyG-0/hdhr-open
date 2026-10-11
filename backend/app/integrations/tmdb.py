"""TMDB (The Movie Database) poster lookup.

Fallback artwork source for builtin-DVR recordings that have no
guide-supplied `image_url`. Unlike app.integrations.schedules_direct, every
failure mode here (no API key configured, network error, no match) is
swallowed and reported as `None` rather than raised — this runs as a
best-effort background backfill, never something a caller needs to handle.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, Literal

import httpx

from app.storage.db import get_network_integration

logger = logging.getLogger(__name__)

API_BASE_URL = "https://api.themoviedb.org/3"
IMAGE_BASE_URL = "https://image.tmdb.org/t/p/w500"
USER_AGENT = "hdhr-open/0.1"
DEFAULT_TIMEOUT = 10.0

Kind = Literal["tv", "movie"]


def _headers() -> dict[str, str]:
    return {"User-Agent": USER_AGENT, "Accept": "application/json"}


def _normalize_title(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


async def _get_api_key() -> str | None:
    row = await asyncio.to_thread(get_network_integration, "tmdb")
    if not row:
        return None
    api_key = row.get("settings", {}).get("api_key")
    return api_key or None


async def _find_best_match(client: httpx.AsyncClient, kind: Kind, title: str, api_key: str) -> dict[str, Any] | None:
    """Search `/search/{kind}` and return the raw matched result dict, or `None`.

    TMDB's search endpoint is fuzzy and routinely returns loosely-related
    or same-named-but-unrelated entries ahead of the obvious match (e.g.
    searching "Cheers" surfaces an unrelated horror film before the real
    sitcom). Only accept results whose title/name is an exact match once
    normalized, and among those prefer the most popular one, so a
    well-known show/movie always wins over an obscure same-named result.
    """
    url = f"{API_BASE_URL}/search/{kind}"
    try:
        resp = await client.get(url, params={"query": title, "api_key": api_key}, headers=_headers())
    except httpx.HTTPError as exc:
        logger.debug("TMDB request failed for %r (%s): %s", title, kind, exc)
        return None

    if resp.status_code != 200:
        logger.debug("TMDB search returned status %d for %r (%s)", resp.status_code, title, kind)
        return None

    try:
        data: Any = resp.json()
    except Exception:
        logger.debug("TMDB returned invalid JSON for %r (%s)", title, kind)
        return None

    results = data.get("results") if isinstance(data, dict) else None
    if not results:
        return None

    query_norm = _normalize_title(title)
    best: dict[str, Any] | None = None
    best_popularity = -1.0
    for result in results:
        if not isinstance(result, dict):
            continue
        poster_path = result.get("poster_path")
        if not poster_path:
            continue
        name = result.get("name") or result.get("title") or ""
        if _normalize_title(name) != query_norm:
            continue
        popularity = result.get("popularity") or 0.0
        if popularity > best_popularity:
            best = result
            best_popularity = popularity

    return best


async def _search(client: httpx.AsyncClient, kind: Kind, title: str, api_key: str) -> str | None:
    best = await _find_best_match(client, kind, title, api_key)
    if best is None:
        return None
    return f"{IMAGE_BASE_URL}{best['poster_path']}"


async def _fetch_details(client: httpx.AsyncClient, kind: Kind, tmdb_id: int, api_key: str) -> dict[str, Any] | None:
    """`GET /{kind}/{tmdb_id}?append_to_response=credits` — one call for both
    the full record and its top-billed cast."""
    url = f"{API_BASE_URL}/{kind}/{tmdb_id}"
    try:
        resp = await client.get(
            url, params={"api_key": api_key, "append_to_response": "credits"}, headers=_headers()
        )
    except httpx.HTTPError as exc:
        logger.debug("TMDB details request failed for %s id=%s: %s", kind, tmdb_id, exc)
        return None

    if resp.status_code != 200:
        logger.debug("TMDB details returned status %d for %s id=%s", resp.status_code, kind, tmdb_id)
        return None

    try:
        data: Any = resp.json()
    except Exception:
        logger.debug("TMDB returned invalid JSON for %s id=%s details", kind, tmdb_id)
        return None

    return data if isinstance(data, dict) else None


async def _fetch_season_episodes(
    client: httpx.AsyncClient, tmdb_id: int, season_number: int, api_key: str
) -> list[dict[str, Any]] | None:
    """`GET /tv/{tmdb_id}/season/{season_number}` and return its `episodes` list, or `None`."""
    url = f"{API_BASE_URL}/tv/{tmdb_id}/season/{season_number}"
    try:
        resp = await client.get(url, params={"api_key": api_key}, headers=_headers())
    except httpx.HTTPError as exc:
        logger.debug("TMDB season request failed for tv id=%s season=%s: %s", tmdb_id, season_number, exc)
        return None

    if resp.status_code != 200:
        logger.debug(
            "TMDB season request returned status %d for tv id=%s season=%s",
            resp.status_code,
            tmdb_id,
            season_number,
        )
        return None

    try:
        data: Any = resp.json()
    except Exception:
        logger.debug("TMDB returned invalid JSON for tv id=%s season=%s", tmdb_id, season_number)
        return None

    episodes = data.get("episodes") if isinstance(data, dict) else None
    return episodes if isinstance(episodes, list) else None


def _match_episode(episodes: list[dict[str, Any]], episode_title: str) -> dict[str, Any] | None:
    """Exact (normalized) title match against a season's episode list -
    same exact-match philosophy as `_find_best_match`. There's no
    popularity signal to break ties within a season, but an exact
    normalized name match is reliable enough that the first one wins."""
    query_norm = _normalize_title(episode_title)
    for episode in episodes:
        if not isinstance(episode, dict):
            continue
        if _normalize_title(episode.get("name") or "") == query_norm:
            return episode
    return None


def _kind_order(kind_hint: Kind | None) -> tuple[Kind, Kind]:
    """`kind_hint` first (defaulting to "tv", since DVR recordings/guide
    airings are more often series episodes than movies), then the other kind
    as a fallback."""
    return ("movie", "tv") if kind_hint == "movie" else ("tv", "movie")


async def search_poster(title: str, kind_hint: Kind | None = None) -> str | None:
    """Look up `title` on TMDB and return a full poster image URL, or `None`.

    Tries `kind_hint` first (defaulting to "tv", since DVR recordings are
    more often series episodes than movies) then falls back to the other
    kind if nothing came back. Only an exact (normalized) title match is
    accepted, so generic/unmatchable titles correctly yield `None` rather
    than an unrelated same-named result. Never raises: an unconfigured API
    key, a network failure, or no match all just produce `None`.
    """
    if not title or not title.strip():
        return None

    api_key = await _get_api_key()
    if not api_key:
        return None

    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        for kind in _kind_order(kind_hint):
            poster_url = await _search(client, kind, title, api_key)
            if poster_url:
                return poster_url

    return None


async def is_configured() -> bool:
    """`True` iff a TMDB API key is configured."""
    return await _get_api_key() is not None


def _genre_names(data: dict[str, Any]) -> list[str]:
    genres = data.get("genres")
    if not isinstance(genres, list):
        return []
    return [g["name"] for g in genres if isinstance(g, dict) and g.get("name")]


def _cast_members(data: dict[str, Any], limit: int = 8) -> list[dict[str, Any]]:
    credits = data.get("credits")
    cast = credits.get("cast") if isinstance(credits, dict) else None
    if not isinstance(cast, list):
        return []
    members = []
    for member in cast[:limit]:
        if not isinstance(member, dict) or not member.get("name"):
            continue
        profile_path = member.get("profile_path")
        members.append(
            {
                "name": member["name"],
                "character": member.get("character") or None,
                "profile_url": f"{IMAGE_BASE_URL}{profile_path}" if profile_path else None,
            }
        )
    return members


async def find_details(
    title: str,
    kind_hint: Kind | None = None,
    episode_title: str | None = None,
    season_number: int | None = None,
) -> dict[str, Any] | None:
    """Look up `title` on TMDB (same exact-match + popularity-ranked search
    and kind_hint-first/fallback ordering as `search_poster`) and return a
    normalized details dict, or `None`.

    For a matched TV series, if `season_number` and `episode_title` are also
    given, additionally fetches that season's episode list and - on an exact
    (normalized) title match - merges episode-specific fields (`episode_name`,
    `episode_overview`, `episode_air_date`, `episode_number`,
    `episode_still_url`) into the result. This is pure best-effort: no
    season/episode match just means those fields are omitted, never an error.

    Never raises: an unconfigured API key, a network failure, or no match
    all just produce `None`.
    """
    if not title or not title.strip():
        return None

    api_key = await _get_api_key()
    if not api_key:
        return None

    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        for kind in _kind_order(kind_hint):
            best = await _find_best_match(client, kind, title, api_key)
            if best is None or best.get("id") is None:
                continue
            details = await _fetch_details(client, kind, best["id"], api_key)
            if details is None:
                continue

            poster_path = details.get("poster_path")
            backdrop_path = details.get("backdrop_path")
            tmdb_id = details.get("id", best["id"])
            result = {
                "kind": kind,
                "tmdb_id": tmdb_id,
                "title": details.get("title") or details.get("name") or title,
                "overview": details.get("overview") or None,
                "poster_url": f"{IMAGE_BASE_URL}{poster_path}" if poster_path else None,
                "backdrop_url": f"{IMAGE_BASE_URL}{backdrop_path}" if backdrop_path else None,
                "vote_average": details.get("vote_average"),
                "genres": _genre_names(details),
                "release_date": details.get("release_date") or None,
                "first_air_date": details.get("first_air_date") or None,
                "runtime_minutes": details.get("runtime"),
                "number_of_seasons": details.get("number_of_seasons"),
                "status": details.get("status") or None,
                "tagline": details.get("tagline") or None,
                "cast": _cast_members(details),
                "episode_name": None,
                "episode_overview": None,
                "episode_air_date": None,
                "episode_number": None,
                "episode_still_url": None,
            }

            if kind == "tv" and season_number is not None and episode_title and episode_title.strip():
                episodes = await _fetch_season_episodes(client, tmdb_id, season_number, api_key)
                matched = _match_episode(episodes, episode_title) if episodes else None
                if matched:
                    still_path = matched.get("still_path")
                    result["episode_name"] = matched.get("name") or None
                    result["episode_overview"] = matched.get("overview") or None
                    result["episode_air_date"] = matched.get("air_date") or None
                    result["episode_number"] = matched.get("episode_number")
                    result["episode_still_url"] = f"{IMAGE_BASE_URL}{still_path}" if still_path else None

            return result

    return None
