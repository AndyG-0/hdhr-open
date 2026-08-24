from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.dvr.builtin import poster_lookup


def test_classify_category():
    assert poster_lookup.classify_category(title="NFL Football", episode_title="Cowboys at Cardinals") == "sports"
    assert poster_lookup.classify_category(title="PGA Tour Golf", category="Sports") == "sports"
    assert poster_lookup.classify_category(title="Premier League Soccer") == "sports"
    assert poster_lookup.classify_category(title="Random Event", episode_title="Team A vs Team B") == "sports"

    assert poster_lookup.classify_category(title="The Matrix", category="Movie") == "movies"
    assert poster_lookup.classify_category(title="Inception", category="feature film") == "movies"
    assert poster_lookup.classify_category(title="Alien", category="cinema") == "movies"

    assert poster_lookup.classify_category(title="Wings", episode_title="Love Means...") == "shows"
    assert poster_lookup.classify_category(title="Cheers") == "shows"
    assert poster_lookup.classify_category(title="NBC Nightly News", category="News") == "shows"
    assert poster_lookup.classify_category(title="Planet Earth", category="Documentary") == "shows"


@pytest.mark.asyncio
async def test_find_poster_for_sports(monkeypatch):
    monkeypatch.setattr(
        poster_lookup.thesportsdb,
        "search_sports_poster",
        AsyncMock(return_value="https://example.com/sports_fanart.jpg"),
    )
    monkeypatch.setattr(
        poster_lookup.tmdb,
        "search_poster",
        AsyncMock(return_value="https://example.com/wrong_tmdb.jpg"),
    )

    poster = await poster_lookup.find_poster_for_program(
        title="NFL Football",
        episode_title="Dallas Cowboys at Arizona Cardinals",
    )
    assert poster == "https://example.com/sports_fanart.jpg"


@pytest.mark.asyncio
async def test_find_poster_for_shows_and_movies(monkeypatch):
    monkeypatch.setattr(
        poster_lookup.tmdb,
        "search_poster",
        AsyncMock(return_value="https://example.com/movie_poster.jpg"),
    )

    poster = await poster_lookup.find_poster_for_program(
        title="Inception",
        category="Movie",
    )
    assert poster == "https://example.com/movie_poster.jpg"
    poster_lookup.tmdb.search_poster.assert_called_with("Inception", "movie")
