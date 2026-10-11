from __future__ import annotations

import pytest
import respx
from httpx import Response

from app.integrations import tmdb
from app.storage import db


@pytest.mark.asyncio
async def test_search_poster_returns_none_when_api_key_unconfigured(tmp_db):
    result = await tmdb.search_poster("The Office")
    assert result is None


@pytest.mark.asyncio
@respx.mock
async def test_search_poster_returns_url_from_tv_search(tmp_db):
    db.save_network_integration("tmdb", "tmdb", "TMDB", {"api_key": "test-key"})
    respx.get("https://api.themoviedb.org/3/search/tv").mock(
        return_value=Response(
            200, json={"results": [{"name": "The Office", "poster_path": "/abc123.jpg", "popularity": 10.0}]}
        )
    )

    result = await tmdb.search_poster("The Office", kind_hint="tv")

    assert result == "https://image.tmdb.org/t/p/w500/abc123.jpg"


@pytest.mark.asyncio
@respx.mock
async def test_search_poster_falls_back_to_movie_when_tv_has_no_results(tmp_db):
    db.save_network_integration("tmdb", "tmdb", "TMDB", {"api_key": "test-key"})
    respx.get("https://api.themoviedb.org/3/search/tv").mock(return_value=Response(200, json={"results": []}))
    respx.get("https://api.themoviedb.org/3/search/movie").mock(
        return_value=Response(
            200, json={"results": [{"title": "Some Movie", "poster_path": "/movie.jpg", "popularity": 5.0}]}
        )
    )

    result = await tmdb.search_poster("Some Movie")

    assert result == "https://image.tmdb.org/t/p/w500/movie.jpg"


@pytest.mark.asyncio
@respx.mock
async def test_search_poster_prefers_movie_first_with_movie_kind_hint(tmp_db):
    db.save_network_integration("tmdb", "tmdb", "TMDB", {"api_key": "test-key"})
    movie_route = respx.get("https://api.themoviedb.org/3/search/movie").mock(
        return_value=Response(
            200, json={"results": [{"title": "Some Movie", "poster_path": "/movie.jpg", "popularity": 5.0}]}
        )
    )
    tv_route = respx.get("https://api.themoviedb.org/3/search/tv").mock(
        return_value=Response(200, json={"results": []})
    )

    result = await tmdb.search_poster("Some Movie", kind_hint="movie")

    assert result == "https://image.tmdb.org/t/p/w500/movie.jpg"
    assert movie_route.called
    assert not tv_route.called


@pytest.mark.asyncio
@respx.mock
async def test_search_poster_skips_results_without_poster_path(tmp_db):
    db.save_network_integration("tmdb", "tmdb", "TMDB", {"api_key": "test-key"})
    respx.get("https://api.themoviedb.org/3/search/tv").mock(
        return_value=Response(
            200,
            json={
                "results": [
                    {"name": "The Office", "poster_path": None},
                    {"name": "The Office", "poster_path": "/second.jpg", "popularity": 8.0},
                ]
            },
        )
    )

    result = await tmdb.search_poster("The Office", kind_hint="tv")

    assert result == "https://image.tmdb.org/t/p/w500/second.jpg"


@pytest.mark.asyncio
@respx.mock
async def test_search_poster_returns_none_on_no_results_at_all(tmp_db):
    db.save_network_integration("tmdb", "tmdb", "TMDB", {"api_key": "test-key"})
    respx.get("https://api.themoviedb.org/3/search/tv").mock(return_value=Response(200, json={"results": []}))
    respx.get("https://api.themoviedb.org/3/search/movie").mock(return_value=Response(200, json={"results": []}))

    result = await tmdb.search_poster("Nonexistent Show")

    assert result is None


@pytest.mark.asyncio
@respx.mock
async def test_search_poster_returns_none_on_http_error(tmp_db):
    db.save_network_integration("tmdb", "tmdb", "TMDB", {"api_key": "test-key"})
    respx.get("https://api.themoviedb.org/3/search/tv").mock(return_value=Response(500))
    respx.get("https://api.themoviedb.org/3/search/movie").mock(return_value=Response(500))

    result = await tmdb.search_poster("The Office")

    assert result is None


@pytest.mark.asyncio
async def test_search_poster_returns_none_for_blank_title(tmp_db):
    db.save_network_integration("tmdb", "tmdb", "TMDB", {"api_key": "test-key"})

    assert await tmdb.search_poster("") is None
    assert await tmdb.search_poster("   ") is None


@pytest.mark.asyncio
@respx.mock
async def test_search_poster_rejects_fuzzy_non_exact_matches(tmp_db):
    """TMDB's search is fuzzy and can return same-word-but-unrelated titles
    ahead of (or instead of) the real match - e.g. searching "Cheers" once
    surfaced an unrelated horror film. Only an exact (normalized) title match
    should ever be accepted."""
    db.save_network_integration("tmdb", "tmdb", "TMDB", {"api_key": "test-key"})
    respx.get("https://api.themoviedb.org/3/search/tv").mock(
        return_value=Response(
            200,
            json={
                "results": [
                    {"name": "Cheers Squad", "poster_path": "/wrong.jpg", "popularity": 99.0},
                ]
            },
        )
    )
    respx.get("https://api.themoviedb.org/3/search/movie").mock(return_value=Response(200, json={"results": []}))

    result = await tmdb.search_poster("Cheers", kind_hint="tv")

    assert result is None


@pytest.mark.asyncio
@respx.mock
async def test_search_poster_prefers_highest_popularity_among_exact_matches(tmp_db):
    """Multiple entries can share the exact same normalized title (reruns,
    specials, foreign remakes); the most popular one is almost always the
    one the user actually recorded."""
    db.save_network_integration("tmdb", "tmdb", "TMDB", {"api_key": "test-key"})
    respx.get("https://api.themoviedb.org/3/search/tv").mock(
        return_value=Response(
            200,
            json={
                "results": [
                    {"name": "Wings", "poster_path": "/obscure.jpg", "popularity": 3.4},
                    {"name": "Wings", "poster_path": "/famous.jpg", "popularity": 35.7},
                    {"name": "Wings", "poster_path": "/other.jpg", "popularity": 5.1},
                ]
            },
        )
    )

    result = await tmdb.search_poster("Wings", kind_hint="tv")

    assert result == "https://image.tmdb.org/t/p/w500/famous.jpg"


@pytest.mark.asyncio
async def test_is_configured_false_without_api_key(tmp_db):
    assert await tmdb.is_configured() is False


@pytest.mark.asyncio
async def test_is_configured_true_with_api_key(tmp_db):
    db.save_network_integration("tmdb", "tmdb", "TMDB", {"api_key": "test-key"})
    assert await tmdb.is_configured() is True


@pytest.mark.asyncio
@respx.mock
async def test_find_details_returns_none_when_api_key_unconfigured(tmp_db):
    result = await tmdb.find_details("The Office")
    assert result is None


@pytest.mark.asyncio
@respx.mock
async def test_find_details_returns_normalized_details_with_cast(tmp_db):
    db.save_network_integration("tmdb", "tmdb", "TMDB", {"api_key": "test-key"})
    respx.get("https://api.themoviedb.org/3/search/tv").mock(
        return_value=Response(
            200,
            json={
                "results": [{"id": 2316, "name": "The Office", "poster_path": "/abc123.jpg", "popularity": 10.0}]
            },
        )
    )
    respx.get("https://api.themoviedb.org/3/tv/2316").mock(
        return_value=Response(
            200,
            json={
                "id": 2316,
                "name": "The Office",
                "overview": "Paper company shenanigans.",
                "poster_path": "/abc123.jpg",
                "backdrop_path": "/backdrop.jpg",
                "vote_average": 8.6,
                "genres": [{"name": "Comedy"}],
                "first_air_date": "2005-03-24",
                "number_of_seasons": 9,
                "status": "Ended",
                "tagline": "Welcome to Dunder Mifflin.",
                "credits": {
                    "cast": [
                        {"name": "Steve Carell", "character": "Michael Scott", "profile_path": "/steve.jpg"},
                        {"name": "No Profile Actor", "character": "Extra", "profile_path": None},
                    ]
                },
            },
        )
    )

    result = await tmdb.find_details("The Office", kind_hint="tv")

    assert result == {
        "kind": "tv",
        "tmdb_id": 2316,
        "title": "The Office",
        "overview": "Paper company shenanigans.",
        "poster_url": "https://image.tmdb.org/t/p/w500/abc123.jpg",
        "backdrop_url": "https://image.tmdb.org/t/p/w500/backdrop.jpg",
        "vote_average": 8.6,
        "genres": ["Comedy"],
        "release_date": None,
        "first_air_date": "2005-03-24",
        "runtime_minutes": None,
        "number_of_seasons": 9,
        "status": "Ended",
        "tagline": "Welcome to Dunder Mifflin.",
        "cast": [
            {"name": "Steve Carell", "character": "Michael Scott", "profile_url": "https://image.tmdb.org/t/p/w500/steve.jpg"},
            {"name": "No Profile Actor", "character": "Extra", "profile_url": None},
        ],
        "episode_name": None,
        "episode_overview": None,
        "episode_air_date": None,
        "episode_number": None,
        "episode_still_url": None,
    }


@pytest.mark.asyncio
@respx.mock
async def test_find_details_merges_matched_episode_fields(tmp_db):
    db.save_network_integration("tmdb", "tmdb", "TMDB", {"api_key": "test-key"})
    respx.get("https://api.themoviedb.org/3/search/tv").mock(
        return_value=Response(
            200,
            json={
                "results": [{"id": 2316, "name": "The Office", "poster_path": "/abc123.jpg", "popularity": 10.0}]
            },
        )
    )
    respx.get("https://api.themoviedb.org/3/tv/2316").mock(
        return_value=Response(200, json={"id": 2316, "name": "The Office"})
    )
    respx.get("https://api.themoviedb.org/3/tv/2316/season/3").mock(
        return_value=Response(
            200,
            json={
                "episodes": [
                    {
                        "name": "The Merger",
                        "overview": "Dunder Mifflin merges with Michael Scott Paper Company.",
                        "air_date": "2006-10-26",
                        "episode_number": 8,
                        "still_path": "/merger.jpg",
                    },
                    {"name": "Grief Counseling", "episode_number": 4},
                ]
            },
        )
    )

    result = await tmdb.find_details("The Office", kind_hint="tv", episode_title="The Merger", season_number=3)

    assert result is not None
    assert result["episode_name"] == "The Merger"
    assert result["episode_overview"] == "Dunder Mifflin merges with Michael Scott Paper Company."
    assert result["episode_air_date"] == "2006-10-26"
    assert result["episode_number"] == 8
    assert result["episode_still_url"] == "https://image.tmdb.org/t/p/w500/merger.jpg"


@pytest.mark.asyncio
@respx.mock
async def test_find_details_omits_episode_fields_on_no_episode_match(tmp_db):
    db.save_network_integration("tmdb", "tmdb", "TMDB", {"api_key": "test-key"})
    respx.get("https://api.themoviedb.org/3/search/tv").mock(
        return_value=Response(
            200,
            json={
                "results": [{"id": 2316, "name": "The Office", "poster_path": "/abc123.jpg", "popularity": 10.0}]
            },
        )
    )
    respx.get("https://api.themoviedb.org/3/tv/2316").mock(
        return_value=Response(200, json={"id": 2316, "name": "The Office"})
    )
    respx.get("https://api.themoviedb.org/3/tv/2316/season/3").mock(
        return_value=Response(200, json={"episodes": [{"name": "Grief Counseling", "episode_number": 4}]})
    )

    result = await tmdb.find_details(
        "The Office", kind_hint="tv", episode_title="Totally Different Title", season_number=3
    )

    assert result is not None
    assert result["episode_name"] is None
    assert result["episode_still_url"] is None


@pytest.mark.asyncio
@respx.mock
async def test_find_details_omits_episode_fields_when_season_request_fails(tmp_db):
    db.save_network_integration("tmdb", "tmdb", "TMDB", {"api_key": "test-key"})
    respx.get("https://api.themoviedb.org/3/search/tv").mock(
        return_value=Response(
            200,
            json={
                "results": [{"id": 2316, "name": "The Office", "poster_path": "/abc123.jpg", "popularity": 10.0}]
            },
        )
    )
    respx.get("https://api.themoviedb.org/3/tv/2316").mock(
        return_value=Response(200, json={"id": 2316, "name": "The Office"})
    )
    respx.get("https://api.themoviedb.org/3/tv/2316/season/3").mock(return_value=Response(404))

    result = await tmdb.find_details("The Office", kind_hint="tv", episode_title="The Merger", season_number=3)

    assert result is not None
    assert result["episode_name"] is None


@pytest.mark.asyncio
@respx.mock
async def test_find_details_skips_episode_lookup_without_season_number(tmp_db):
    db.save_network_integration("tmdb", "tmdb", "TMDB", {"api_key": "test-key"})
    respx.get("https://api.themoviedb.org/3/search/tv").mock(
        return_value=Response(
            200,
            json={
                "results": [{"id": 2316, "name": "The Office", "poster_path": "/abc123.jpg", "popularity": 10.0}]
            },
        )
    )
    respx.get("https://api.themoviedb.org/3/tv/2316").mock(
        return_value=Response(200, json={"id": 2316, "name": "The Office"})
    )

    result = await tmdb.find_details("The Office", kind_hint="tv", episode_title="The Merger")

    assert result is not None
    assert result["episode_name"] is None


@pytest.mark.asyncio
@respx.mock
async def test_find_details_returns_none_on_no_match(tmp_db):
    db.save_network_integration("tmdb", "tmdb", "TMDB", {"api_key": "test-key"})
    respx.get("https://api.themoviedb.org/3/search/tv").mock(return_value=Response(200, json={"results": []}))
    respx.get("https://api.themoviedb.org/3/search/movie").mock(return_value=Response(200, json={"results": []}))

    result = await tmdb.find_details("Nonexistent Show")

    assert result is None
