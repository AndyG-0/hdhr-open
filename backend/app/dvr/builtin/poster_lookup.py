"""Unified poster lookup and category classification for recordings.

Combines TMDb (for movies and TV series) and TheSportsDB (for sports) to find
high-quality poster/fanart artwork.
"""

from __future__ import annotations

import logging
import re
from typing import Literal

from app.integrations import thesportsdb, tmdb

logger = logging.getLogger(__name__)

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
