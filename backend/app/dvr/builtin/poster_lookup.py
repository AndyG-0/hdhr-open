"""Unified poster lookup and category classification for recordings.

Combines TMDb (for movies and TV series) and TheSportsDB (for sports) to find
high-quality poster/fanart artwork.
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from app.integrations import thesportsdb, tmdb
from app.storage import db

logger = logging.getLogger(__name__)

# Conservative concurrency cap for batch backfill: polite to TheSportsDB's
# free shared tier and comfortably under TMDb's ~40 req/10s limit. These
# backfills run unattended on background jobs, so throughput matters less
# than not hammering a shared free API.
_BACKFILL_CONCURRENCY = 5

# Confirmed misses are retried after this long, in case a title is later
# added to TMDb/TheSportsDB. Confirmed hits are never expired.
_MISS_TTL = timedelta(days=30)

CategoryType = Literal["shows", "movies", "sports"]

SPORTS_KEYWORDS = [
    "sport",
    "sports",
    "football",
    "basketball",
    "baseball",
    "hockey",
    "soccer",
    "golf",
    "tennis",
    "racing",
    "nascar",
    "formula 1",
    "f1",
    "olympics",
    "wrestling",
    "boxing",
    "mma",
    "ufc",
    "wwe",
    "nfl",
    "nba",
    "mlb",
    "nhl",
    "pga",
    "mls",
    "premier league",
    "champions league",
    "uefa",
    "fifa",
    "ncaa",
    "college football",
    "college basketball",
]

MOVIE_KEYWORDS = ["movie", "feature film", "film", "cinema"]


def classify_category(
    title: str = "",
    episode_title: str | None = None,
    category: str | None = None,
) -> CategoryType:
    """Classify a program into 'sports', 'movies', or 'shows' based on metadata."""
    t = (title or "").lower()
    ep = (episode_title or "").lower()
    cat = (category or "").lower()

    # 1. Check explicit guide category first if present
    if any(k in cat for k in SPORTS_KEYWORDS):
        return "sports"
    if any(k in cat for k in MOVIE_KEYWORDS):
        return "movies"
    if "series" in cat or "news" in cat or "tvshow" in cat or "episode" in cat or "comedy" in cat or "drama" in cat:
        return "shows"

    # 2. Check title keywords
    if any(re.search(r"\b" + re.escape(k) + r"\b", t) for k in SPORTS_KEYWORDS):
        return "sports"
    if any(re.search(r"\b" + re.escape(k) + r"\b", t) for k in MOVIE_KEYWORDS):
        return "movies"

    # 3. Check matchup patterns in episode_title (e.g. "Cowboys at Cardinals")
    if " at " in ep or " vs " in ep or " vs. " in ep or " @ " in ep:
        return "sports"

    # 4. Default to shows (TV shows / series / news / general TV)
    return "shows"


async def find_poster_for_program(
    title: str,
    episode_title: str | None = None,
    season_number: int | None = None,
    episode_number: int | None = None,
    category: str | None = None,
) -> str | None:
    """Find a poster or fanart URL across TheSportsDB and TMDb."""
    cat_type = classify_category(title, episode_title, category)

    if cat_type == "sports":
        # 1. Try TheSportsDB for sports
        try:
            sports_poster = await thesportsdb.search_sports_poster(title, episode_title)
            if sports_poster:
                return sports_poster
        except Exception:
            logger.debug("TheSportsDB lookup failed for %s", title, exc_info=True)

    # 2. Try TMDb (for movies, shows, or fallback)
    try:
        kind_hint: tmdb.Kind = "movie" if cat_type == "movies" else "tv"
        tmdb_poster = await tmdb.search_poster(title, kind_hint)
        if tmdb_poster:
            return tmdb_poster
    except Exception:
        logger.debug("TMDb lookup failed for %s", title, exc_info=True)

    # 3. Fallback: if category wasn't initially detected as sports but TMDb returned nothing,
    # try sports search as a safety fallback (e.g. obscure tournament)
    if cat_type != "sports":
        try:
            return await thesportsdb.search_sports_poster(title, episode_title)
        except Exception:
            pass

    return None


def _normalize_key_part(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "", (value or "").lower())


def build_cache_key(
    title: str,
    episode_title: str | None = None,
    category: str | None = None,
) -> str:
    """Bucket-qualified normalized cache key, so e.g. a movie and an
    unrelated sports event that happen to share a title never collide."""
    cat_type = classify_category(title, episode_title, category)
    return f"{cat_type}:{_normalize_key_part(title)}|{_normalize_key_part(episode_title)}"


async def find_poster_cached(
    title: str,
    episode_title: str | None = None,
    season_number: int | None = None,
    episode_number: int | None = None,
    category: str | None = None,
) -> str | None:
    """Cache-first wrapper around `find_poster_for_program`. A cache hit
    (including a confirmed miss) never re-queries TMDb/TheSportsDB; a cache
    miss resolves once and writes the result back (hit or miss) so every
    other caller - guide ingestion, discovery, recording-completion backfill -
    shares the same result going forward."""
    cache_key = build_cache_key(title, episode_title, category)
    cached = await asyncio.to_thread(db.get_cached_posters, [cache_key])
    if cache_key in cached:
        return cached[cache_key]["poster_url"]

    poster_url = await find_poster_for_program(
        title, episode_title, season_number, episode_number, category
    )
    await asyncio.to_thread(
        db.upsert_poster_cache,
        [
            {
                "cache_key": cache_key,
                "category": classify_category(title, episode_title, category),
                "poster_url": poster_url,
                "looked_up_at": datetime.now(UTC).isoformat(),
            }
        ],
    )
    return poster_url


async def backfill_missing_images(
    rows: list[dict[str, Any]],
    *,
    write_back: Callable[[dict[str, Any], str], Awaitable[None]] | None = None,
) -> int:
    """Resolve posters for any row missing `image_url`, bounded by a
    concurrency cap. Mutates `row["image_url"]` in place for resolved rows;
    if `write_back` is given, it's awaited for each resolved row so the
    caller can persist the result elsewhere (e.g. `guide_programs`). Returns
    the count of rows backfilled."""
    targets = [row for row in rows if not row.get("image_url")]
    if not targets:
        return 0

    semaphore = asyncio.Semaphore(_BACKFILL_CONCURRENCY)

    async def _resolve(row: dict[str, Any]) -> bool:
        async with semaphore:
            poster_url = await find_poster_cached(
                row.get("title") or "",
                row.get("episode_title"),
                row.get("season_number"),
                row.get("episode_number"),
                row.get("category"),
            )
        if not poster_url:
            return False
        row["image_url"] = poster_url
        if write_back is not None:
            await write_back(row, poster_url)
        return True

    resolved = await asyncio.gather(*(_resolve(row) for row in targets))
    return sum(1 for was_resolved in resolved if was_resolved)


async def cleanup_expired_poster_cache() -> None:
    """Purge confirmed misses older than the retry TTL. Confirmed hits are
    never expired - posters don't change once found."""
    cutoff = (datetime.now(UTC) - _MISS_TTL).isoformat()
    await asyncio.to_thread(db.delete_expired_poster_cache, cutoff)
