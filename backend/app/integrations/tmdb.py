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


async def _search(client: httpx.AsyncClient, kind: Kind, title: str, api_key: str) -> str | None:
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

    # TMDB's search endpoint is fuzzy and routinely returns loosely-related
    # or same-named-but-unrelated entries ahead of the obvious match (e.g.
    # searching "Cheers" surfaces an unrelated horror film before the real
    # sitcom). Only accept results whose title/name is an exact match once
    # normalized, and among those prefer the most popular one, so a
    # well-known show/movie always wins over an obscure same-named result.
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

    if best is None:
        return None

    return f"{IMAGE_BASE_URL}{best['poster_path']}"


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

    kinds: tuple[Kind, Kind] = ("movie", "tv") if kind_hint == "movie" else ("tv", "movie")

    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        for kind in kinds:
            poster_url = await _search(client, kind, title, api_key)
            if poster_url:
                return poster_url

    return None
