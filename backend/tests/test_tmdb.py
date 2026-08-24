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
