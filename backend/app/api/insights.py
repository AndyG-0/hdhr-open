"""Player "Insights" data: TMDB details for movies/shows, best-effort live
score/status for sports.

Reads are open to any logged-in user (same split as app.api.sports — no
admin gating needed for a read-only lookup).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.auth import get_current_user
from app.dvr.builtin.poster_lookup import classify_category
from app.integrations import thesportsdb, tmdb
from app.storage.cache import cache

router = APIRouter(prefix="/api/insights", tags=["insights"], dependencies=[Depends(get_current_user)])

# TMDB overview/cast/rating essentially never change within a day, so a long
# TTL avoids re-fetching on every modal open. Sports event details are
# deliberately never cached (see thesportsdb.get_event_details).
_TMDB_CACHE_TTL_SECONDS = 6 * 3600


class CastMember(BaseModel):
    name: str
    character: str | None = None
    profile_url: str | None = None


class ProgramInsights(BaseModel):
    kind: Literal["movie", "tv"]
    tmdb_id: int
    title: str
    overview: str | None = None
    poster_url: str | None = None
    backdrop_url: str | None = None
    vote_average: float | None = None
    genres: list[str] = []
    release_date: str | None = None
    first_air_date: str | None = None
    runtime_minutes: int | None = None
    number_of_seasons: int | None = None
    status: str | None = None
    tagline: str | None = None
    cast: list[CastMember] = []
    episode_name: str | None = None
    episode_overview: str | None = None
    episode_air_date: str | None = None
    episode_number: int | None = None
    episode_still_url: str | None = None


class SportsEventInsights(BaseModel):
    status: Literal["scheduled", "live", "finished"] | None = None
    home_team: str | None = None
    away_team: str | None = None
    home_score: int | None = None
    away_score: int | None = None
    venue: str | None = None
    league: str | None = None
    date_event: str | None = None
    time: str | None = None


class InsightsResponse(BaseModel):
    category: Literal["shows", "movies", "sports"]
    tmdb_configured: bool
    tmdb: ProgramInsights | None = None
    sports: SportsEventInsights | None = None


@router.get("/program", response_model=InsightsResponse)
async def get_program_insights(
    title: str,
    episode_title: str | None = None,
    season_number: int | None = None,
    episode_number: int | None = None,
    category: str | None = None,
    start_ts: float | None = None,
) -> InsightsResponse:
    cat_type = classify_category(title, episode_title, category)
    tmdb_configured = await tmdb.is_configured()

    if cat_type == "sports":
        sports_details = None
        teams = thesportsdb.extract_matchup_teams(episode_title or title)
        if len(teams) == 2:
            # Disambiguates which occurrence of a recurring matchup (e.g. an
            # annual rivalry game) TheSportsDB should return - without this,
            # a lookup for a currently-airing game can match a past, already
            # "finished" instance of the same matchup instead.
            event_date = datetime.fromtimestamp(start_ts, tz=UTC).date() if start_ts else None
            try:
                sports_details = await thesportsdb.get_event_details(teams[0], teams[1], event_date)
            except Exception:
                sports_details = None
        return InsightsResponse(
            category=cat_type,
            tmdb_configured=tmdb_configured,
            sports=SportsEventInsights(**sports_details) if sports_details else None,
        )

    episode_key_part = (episode_title or "").strip().lower()
    cache_key = f"insights:tmdb:{cat_type}:{title.strip().lower()}:{episode_key_part}"
    cached: ProgramInsights | None = cache.get(cache_key)
    if cached is not None:
        return InsightsResponse(category=cat_type, tmdb_configured=tmdb_configured, tmdb=cached)

    details = None
    try:
        kind_hint: tmdb.Kind = "movie" if cat_type == "movies" else "tv"
        raw = await tmdb.find_details(title, kind_hint, episode_title=episode_title, season_number=season_number)
        if raw:
            details = ProgramInsights(**raw)
            cache.set(cache_key, details, _TMDB_CACHE_TTL_SECONDS)
    except Exception:
        details = None

    return InsightsResponse(category=cat_type, tmdb_configured=tmdb_configured, tmdb=details)
