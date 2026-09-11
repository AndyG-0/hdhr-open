from __future__ import annotations

from datetime import date

import httpx
import pytest
import respx

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
        respx_mock.get(url__startswith=thesportsdb.API_BASE_URL).mock(
            side_effect=httpx.ConnectError("Connection refused")
        )

        # For a title without a predefined league match
        poster = await thesportsdb.search_sports_poster("Local Sports Event", "School A vs School B")
        assert poster is None


@pytest.mark.asyncio
async def test_get_event_status_finished():
    with respx.mock(base_url=thesportsdb.API_BASE_URL) as respx_mock:
        respx_mock.get("/searchevents.php", params={"e": "Dallas_Cowboys_vs_Arizona_Cardinals"}).respond(
            200,
            json={"event": [{"strStatus": "Match Finished", "dateEvent": "2024-01-01"}]},
        )

        status = await thesportsdb.get_event_status("Dallas Cowboys", "Arizona Cardinals", date(2024, 1, 1))
        assert status == "finished"


@pytest.mark.asyncio
async def test_get_event_status_falls_back_to_reversed_team_order():
    with respx.mock(base_url=thesportsdb.API_BASE_URL) as respx_mock:
        respx_mock.get("/searchevents.php", params={"e": "Lakers_vs_Warriors"}).respond(200, json={"event": None})
        respx_mock.get("/searchevents.php", params={"e": "Warriors_vs_Lakers"}).respond(
            200,
            json={"event": [{"strStatus": "Q3", "dateEvent": "2024-02-02"}]},
        )

        status = await thesportsdb.get_event_status("Lakers", "Warriors", date(2024, 2, 2))
        assert status == "live"


@pytest.mark.asyncio
async def test_get_event_status_scheduled():
    with respx.mock(base_url=thesportsdb.API_BASE_URL) as respx_mock:
        respx_mock.get("/searchevents.php", params={"e": "Arsenal_vs_Chelsea"}).respond(
            200,
            json={"event": [{"strStatus": "NS", "dateEvent": "2024-03-03"}]},
        )

        status = await thesportsdb.get_event_status("Arsenal", "Chelsea", date(2024, 3, 3))
        assert status == "scheduled"


@pytest.mark.asyncio
async def test_get_event_status_none_when_no_event_found():
    with respx.mock(base_url=thesportsdb.API_BASE_URL) as respx_mock:
        respx_mock.get("/searchevents.php", params={"e": "Nobody_vs_Nowhere"}).respond(200, json={"event": None})
        respx_mock.get("/searchevents.php", params={"e": "Nowhere_vs_Nobody"}).respond(200, json={"event": None})

        status = await thesportsdb.get_event_status("Nobody", "Nowhere")
        assert status is None


@pytest.mark.asyncio
async def test_get_event_status_degrades_gracefully_on_network_error():
    with respx.mock(base_url=thesportsdb.API_BASE_URL) as respx_mock:
        respx_mock.get(url__startswith=thesportsdb.API_BASE_URL).mock(
            side_effect=httpx.ConnectError("Connection refused")
        )

        status = await thesportsdb.get_event_status("Team A", "Team B")
        assert status is None
