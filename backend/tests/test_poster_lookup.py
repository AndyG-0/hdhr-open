from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from app.dvr.builtin import poster_lookup
from app.storage import db


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


def test_build_cache_key_is_bucket_qualified():
    movie_key = poster_lookup.build_cache_key("Alien", category="Movie")
    sports_key = poster_lookup.build_cache_key("Alien", category="Sports")
    assert movie_key != sports_key

    # Case/punctuation-insensitive within the same bucket
    assert poster_lookup.build_cache_key("The Matrix!", category="Movie") == poster_lookup.build_cache_key(
        "the matrix", category="Movie"
    )


@pytest.mark.asyncio
async def test_find_poster_cached_writes_through_on_miss(tmp_db, monkeypatch):
    lookup = AsyncMock(return_value="https://example.com/poster.jpg")
    monkeypatch.setattr(poster_lookup, "find_poster_for_program", lookup)

    poster = await poster_lookup.find_poster_cached(title="Inception", category="Movie")
    assert poster == "https://example.com/poster.jpg"
    lookup.assert_awaited_once()

    cache_key = poster_lookup.build_cache_key("Inception", category="Movie")
    cached = db.get_cached_posters([cache_key])
    assert cached[cache_key]["poster_url"] == "https://example.com/poster.jpg"


@pytest.mark.asyncio
async def test_find_poster_cached_skips_lookup_on_hit(tmp_db, monkeypatch):
    lookup = AsyncMock(return_value="https://example.com/should-not-be-used.jpg")
    monkeypatch.setattr(poster_lookup, "find_poster_for_program", lookup)

    cache_key = poster_lookup.build_cache_key("Inception", category="Movie")
    db.upsert_poster_cache(
        [
            {
                "cache_key": cache_key,
                "category": "movies",
                "poster_url": "https://example.com/cached.jpg",
                "looked_up_at": datetime.now(UTC).isoformat(),
            }
        ]
    )

    poster = await poster_lookup.find_poster_cached(title="Inception", category="Movie")
    assert poster == "https://example.com/cached.jpg"
    lookup.assert_not_awaited()


@pytest.mark.asyncio
async def test_find_poster_cached_persists_confirmed_miss(tmp_db, monkeypatch):
    monkeypatch.setattr(poster_lookup, "find_poster_for_program", AsyncMock(return_value=None))

    poster = await poster_lookup.find_poster_cached(title="Some Obscure Show")
    assert poster is None

    cache_key = poster_lookup.build_cache_key("Some Obscure Show")
    cached = db.get_cached_posters([cache_key])
    assert cache_key in cached
    assert cached[cache_key]["poster_url"] is None


@pytest.mark.asyncio
async def test_backfill_missing_images_skips_rows_with_existing_image(tmp_db, monkeypatch):
    find_cached = AsyncMock(return_value="https://example.com/new.jpg")
    monkeypatch.setattr(poster_lookup, "find_poster_cached", find_cached)

    rows = [
        {"title": "Has Image", "image_url": "https://example.com/existing.jpg"},
        {"title": "Missing Image", "image_url": None},
    ]
    count = await poster_lookup.backfill_missing_images(rows)

    assert count == 1
    find_cached.assert_awaited_once()
    assert rows[0]["image_url"] == "https://example.com/existing.jpg"
    assert rows[1]["image_url"] == "https://example.com/new.jpg"


@pytest.mark.asyncio
async def test_backfill_missing_images_invokes_write_back_only_for_resolved_rows(tmp_db, monkeypatch):
    async def fake_find_cached(title, episode_title=None, season_number=None, episode_number=None, category=None):
        return "https://example.com/found.jpg" if title == "Found Show" else None

    monkeypatch.setattr(poster_lookup, "find_poster_cached", fake_find_cached)

    rows = [
        {"title": "Found Show", "image_url": None},
        {"title": "Not Found Show", "image_url": None},
    ]
    write_back = AsyncMock()
    count = await poster_lookup.backfill_missing_images(rows, write_back=write_back)

    assert count == 1
    write_back.assert_awaited_once_with(rows[0], "https://example.com/found.jpg")


@pytest.mark.asyncio
async def test_backfill_missing_images_respects_concurrency_cap(tmp_db, monkeypatch):
    in_flight = 0
    max_in_flight = 0

    async def fake_find_cached(title, episode_title=None, season_number=None, episode_number=None, category=None):
        nonlocal in_flight, max_in_flight
        in_flight += 1
        max_in_flight = max(max_in_flight, in_flight)
        try:
            import asyncio

            await asyncio.sleep(0)
        finally:
            in_flight -= 1
        return None

    monkeypatch.setattr(poster_lookup, "find_poster_cached", fake_find_cached)

    rows = [{"title": f"Show {i}", "image_url": None} for i in range(20)]
    await poster_lookup.backfill_missing_images(rows)

    assert max_in_flight <= poster_lookup._BACKFILL_CONCURRENCY


@pytest.mark.asyncio
async def test_cleanup_expired_poster_cache_only_purges_confirmed_misses(tmp_db):
    old = (datetime.now(UTC) - timedelta(days=31)).isoformat()
    db.upsert_poster_cache(
        [
            {
                "cache_key": "movies:oldhit",
                "category": "movies",
                "poster_url": "https://example.com/hit.jpg",
                "looked_up_at": old,
            },
            {"cache_key": "movies:oldmiss", "category": "movies", "poster_url": None, "looked_up_at": old},
        ]
    )

    await poster_lookup.cleanup_expired_poster_cache()

    remaining = db.get_cached_posters(["movies:oldhit", "movies:oldmiss"])
    assert "movies:oldhit" in remaining
    assert "movies:oldmiss" not in remaining
