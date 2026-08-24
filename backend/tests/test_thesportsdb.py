from __future__ import annotations

import pytest
import respx
import httpx

from app.integrations import thesportsdb


def test_extract_matchup_teams():
    assert thesportsdb.extract_matchup_teams("Dallas Cowboys at Arizona Cardinals") == [
        "Dallas Cowboys",
        "Arizona Cardinals",
    ]
    assert thesportsdb.extract_matchup_teams("Arsenal vs Chelsea") == ["Arsenal", "Chelsea"]
    assert thesportsdb.extract_matchup_teams("#1 Texas vs. #5 Georgia") == ["Texas", "Georgia"]
    assert thesportsdb.extract_matchup_teams("No. 12 Utah @ Arizona") == ["Utah", "Arizona"]
    assert thesportsdb.extract_matchup_teams("Super Bowl LVIII") == ["Super Bowl LVIII"]
    assert thesportsdb.extract_matchup_teams("") == []


@pytest.mark.asyncio
async def test_search_sports_poster_finds_team_fanart():
    thesportsdb._sports_cache.clear()
    with respx.mock(base_url=thesportsdb.API_BASE_URL) as respx_mock:
        respx_mock.get("/searchteams.php?t=Dallas%20Cowboys").respond(
            200,
            json={
                "teams": [
                    {
                        "strTeam": "Dallas Cowboys",
                        "strBadge": "https://example.com/cowboys_badge.png",
                        "strFanart1": "https://example.com/cowboys_fanart.jpg",
                        "strBanner": "https://example.com/cowboys_banner.jpg",
                    }
                ]
            },
        )

        poster = await thesportsdb.search_sports_poster("NFL Football", "Dallas Cowboys at Arizona Cardinals")
        assert poster == "https://example.com/cowboys_fanart.jpg"

        # Cached on subsequent call
        poster_cached = await thesportsdb.search_sports_poster("NFL Football", "Dallas Cowboys at Arizona Cardinals")
        assert poster_cached == poster


@pytest.mark.asyncio
async def test_search_sports_poster_falls_back_to_league_badge():
    thesportsdb._sports_cache.clear()
    with respx.mock(base_url=thesportsdb.API_BASE_URL) as respx_mock:
        respx_mock.get("/searchteams.php?t=Unknown%20Team").respond(200, json={"teams": None})

        poster = await thesportsdb.search_sports_poster("NBA Basketball", "Unknown Team")
        assert poster == thesportsdb.LEAGUE_LOGOS["nba"]


@pytest.mark.asyncio
async def test_search_sports_poster_degrades_gracefully_on_network_error():
    thesportsdb._sports_cache.clear()
    with respx.mock(base_url=thesportsdb.API_BASE_URL) as respx_mock:
        respx_mock.get(url__startswith=thesportsdb.API_BASE_URL).mock(side_effect=httpx.ConnectError("Connection refused"))

        # For a title without a predefined league match
        poster = await thesportsdb.search_sports_poster("Local Sports Event", "School A vs School B")
        assert poster is None
