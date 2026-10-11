from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import insights as insights_api
from app.auth import get_current_user
from app.storage.cache import cache


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(insights_api.router)
    return app


@pytest.fixture
def client():
    app = _app()
    app.dependency_overrides[get_current_user] = lambda: {"id": "member", "role": "member"}
    return TestClient(app)


@pytest.fixture
def unauthenticated_client():
    return TestClient(_app())


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.delete_prefix("insights:")
    yield
    cache.delete_prefix("insights:")


def test_program_insights_requires_login(unauthenticated_client):
    response = unauthenticated_client.get("/api/insights/program", params={"title": "Inception"})
    assert response.status_code == 401


def test_program_insights_for_movie(client, monkeypatch):
    monkeypatch.setattr(insights_api.tmdb, "is_configured", AsyncMock(return_value=True))
    monkeypatch.setattr(
        insights_api.tmdb,
        "find_details",
        AsyncMock(
            return_value={
                "kind": "movie",
                "tmdb_id": 27205,
                "title": "Inception",
                "overview": "A thief who steals secrets.",
                "poster_url": "https://image.tmdb.org/t/p/w500/inception.jpg",
                "backdrop_url": None,
                "vote_average": 8.4,
                "genres": ["Action", "Science Fiction"],
                "release_date": "2010-07-15",
                "first_air_date": None,
                "runtime_minutes": 148,
                "number_of_seasons": None,
                "status": "Released",
                "tagline": "Your mind is the scene of the crime.",
                "cast": [{"name": "Leonardo DiCaprio", "character": "Cobb", "profile_url": None}],
            }
        ),
    )

    response = client.get("/api/insights/program", params={"title": "Inception", "category": "Movie"})

    assert response.status_code == 200
    body = response.json()
    assert body["category"] == "movies"
    assert body["tmdb_configured"] is True
    assert body["sports"] is None
    assert body["tmdb"]["tmdb_id"] == 27205
    assert body["tmdb"]["cast"][0]["name"] == "Leonardo DiCaprio"
    insights_api.tmdb.find_details.assert_called_with("Inception", "movie", episode_title=None, season_number=None)


def test_program_insights_caches_tmdb_lookup(client, monkeypatch):
    monkeypatch.setattr(insights_api.tmdb, "is_configured", AsyncMock(return_value=True))
    find_details = AsyncMock(
        return_value={
            "kind": "tv",
            "tmdb_id": 2316,
            "title": "The Office",
            "overview": None,
            "poster_url": None,
            "backdrop_url": None,
            "vote_average": None,
            "genres": [],
            "release_date": None,
            "first_air_date": None,
            "runtime_minutes": None,
            "number_of_seasons": None,
            "status": None,
            "tagline": None,
            "cast": [],
        }
    )
    monkeypatch.setattr(insights_api.tmdb, "find_details", find_details)

    first = client.get("/api/insights/program", params={"title": "The Office"})
    second = client.get("/api/insights/program", params={"title": "The Office"})

    assert first.status_code == second.status_code == 200
    assert first.json()["tmdb"]["tmdb_id"] == second.json()["tmdb"]["tmdb_id"] == 2316
    find_details.assert_called_once()


def test_program_insights_passes_episode_title_and_season_for_shows(client, monkeypatch):
    monkeypatch.setattr(insights_api.tmdb, "is_configured", AsyncMock(return_value=True))
    find_details = AsyncMock(
        return_value={
            "kind": "tv",
            "tmdb_id": 2316,
            "title": "The Office",
            "overview": None,
            "poster_url": None,
            "backdrop_url": None,
            "vote_average": None,
            "genres": [],
            "release_date": None,
            "first_air_date": None,
            "runtime_minutes": None,
            "number_of_seasons": None,
            "status": None,
            "tagline": None,
            "cast": [],
            "episode_name": "The Merger",
            "episode_overview": "The merger happens.",
            "episode_air_date": "2006-10-26",
            "episode_number": 8,
            "episode_still_url": "https://image.tmdb.org/t/p/w500/merger.jpg",
        }
    )
    monkeypatch.setattr(insights_api.tmdb, "find_details", find_details)

    response = client.get(
        "/api/insights/program",
        params={"title": "The Office", "episode_title": "The Merger", "season_number": 3},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["tmdb"]["episode_name"] == "The Merger"
    assert body["tmdb"]["episode_number"] == 8
    find_details.assert_called_with("The Office", "tv", episode_title="The Merger", season_number=3)


def test_program_insights_cache_key_differentiates_by_episode(client, monkeypatch):
    monkeypatch.setattr(insights_api.tmdb, "is_configured", AsyncMock(return_value=True))

    def _details_for(episode_title=None, **kwargs):
        return {
            "kind": "tv",
            "tmdb_id": 2316,
            "title": "The Office",
            "overview": None,
            "poster_url": None,
            "backdrop_url": None,
            "vote_average": None,
            "genres": [],
            "release_date": None,
            "first_air_date": None,
            "runtime_minutes": None,
            "number_of_seasons": None,
            "status": None,
            "tagline": None,
            "cast": [],
            "episode_name": episode_title,
            "episode_overview": None,
            "episode_air_date": None,
            "episode_number": None,
            "episode_still_url": None,
        }

    find_details = AsyncMock(
        side_effect=lambda title, kind_hint, episode_title=None, season_number=None: _details_for(episode_title)
    )
    monkeypatch.setattr(insights_api.tmdb, "find_details", find_details)

    first = client.get(
        "/api/insights/program", params={"title": "The Office", "episode_title": "The Merger", "season_number": 3}
    )
    second = client.get(
        "/api/insights/program",
        params={"title": "The Office", "episode_title": "Grief Counseling", "season_number": 3},
    )

    assert first.json()["tmdb"]["episode_name"] == "The Merger"
    assert second.json()["tmdb"]["episode_name"] == "Grief Counseling"
    assert find_details.call_count == 2


def test_program_insights_tmdb_not_configured(client, monkeypatch):
    monkeypatch.setattr(insights_api.tmdb, "is_configured", AsyncMock(return_value=False))
    find_details = AsyncMock(return_value=None)
    monkeypatch.setattr(insights_api.tmdb, "find_details", find_details)

    response = client.get("/api/insights/program", params={"title": "Some Show"})

    assert response.status_code == 200
    body = response.json()
    assert body["tmdb_configured"] is False
    assert body["tmdb"] is None


def test_program_insights_for_sports_with_matchup(client, monkeypatch):
    monkeypatch.setattr(insights_api.tmdb, "is_configured", AsyncMock(return_value=True))
    monkeypatch.setattr(
        insights_api.thesportsdb,
        "get_event_details",
        AsyncMock(
            return_value={
                "status": "live",
                "home_team": "Dallas Cowboys",
                "away_team": "Arizona Cardinals",
                "home_score": 17,
                "away_score": 10,
                "venue": "AT&T Stadium",
                "league": "NFL",
                "date_event": "2024-01-01",
                "time": "20:00:00",
            }
        ),
    )

    response = client.get(
        "/api/insights/program",
        params={"title": "NFL Football", "episode_title": "Dallas Cowboys at Arizona Cardinals", "category": "Sports"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["category"] == "sports"
    assert body["tmdb"] is None
    assert body["sports"]["status"] == "live"
    assert body["sports"]["home_score"] == 17


def test_program_insights_for_sports_passes_event_date_from_start_ts(client, monkeypatch):
    monkeypatch.setattr(insights_api.tmdb, "is_configured", AsyncMock(return_value=True))
    get_event_details = AsyncMock(return_value=None)
    monkeypatch.setattr(insights_api.thesportsdb, "get_event_details", get_event_details)

    response = client.get(
        "/api/insights/program",
        params={
            "title": "NFL Football",
            "episode_title": "Dallas Cowboys at Arizona Cardinals",
            "category": "Sports",
            "start_ts": 1704146400,
        },
    )

    assert response.status_code == 200
    get_event_details.assert_called_once()
    args = get_event_details.call_args.args
    assert args[0] == "Dallas Cowboys"
    assert args[1] == "Arizona Cardinals"
    assert args[2] is not None
    assert args[2].isoformat() == "2024-01-01"


def test_program_insights_for_sports_without_parseable_matchup(client, monkeypatch):
    monkeypatch.setattr(insights_api.tmdb, "is_configured", AsyncMock(return_value=True))
    get_event_details = AsyncMock(return_value=None)
    monkeypatch.setattr(insights_api.thesportsdb, "get_event_details", get_event_details)

    response = client.get(
        "/api/insights/program",
        params={"title": "NFL Football", "episode_title": "Super Bowl LVIII", "category": "Sports"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["category"] == "sports"
    assert body["sports"] is None
    get_event_details.assert_not_called()
