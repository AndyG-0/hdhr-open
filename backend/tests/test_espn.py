from __future__ import annotations

import httpx
import pytest
import respx

from app.integrations import espn


@pytest.mark.asyncio
async def test_list_league_teams_parses_response():
    espn._teams_cache.clear()
    with respx.mock(base_url=espn.API_BASE_URL) as respx_mock:
        respx_mock.get("/football/nfl/teams").respond(
            200,
            json={
                "sports": [
                    {
                        "leagues": [
                            {
                                "teams": [
                                    {
                                        "team": {
                                            "id": "6",
                                            "displayName": "Dallas Cowboys",
                                            "abbreviation": "DAL",
                                            "logos": [{"href": "https://example.com/dal.png"}],
                                        }
                                    }
                                ]
                            }
                        ]
                    }
                ]
            },
        )

        teams = await espn.list_league_teams("nfl")
        assert teams == [
            {
                "id": "6",
                "display_name": "Dallas Cowboys",
                "abbreviation": "DAL",
                "logo_url": "https://example.com/dal.png",
            }
        ]

        # Cached on subsequent call - no second HTTP call needed
        teams_cached = await espn.list_league_teams("nfl")
        assert teams_cached == teams


@pytest.mark.asyncio
async def test_list_league_teams_unknown_league():
    assert await espn.list_league_teams("not-a-real-league") is None


@pytest.mark.asyncio
async def test_list_league_teams_degrades_gracefully_on_network_error():
    espn._teams_cache.clear()
    with respx.mock(base_url=espn.API_BASE_URL) as respx_mock:
        respx_mock.get(url__startswith=espn.API_BASE_URL).mock(side_effect=httpx.ConnectError("Connection refused"))

        teams = await espn.list_league_teams("nfl")
        assert teams is None


@pytest.mark.asyncio
async def test_list_league_teams_degrades_on_unexpected_shape():
    espn._teams_cache.clear()
    with respx.mock(base_url=espn.API_BASE_URL) as respx_mock:
        respx_mock.get("/football/nfl/teams").respond(200, json={"unexpected": "shape"})

        teams = await espn.list_league_teams("nfl")
        assert teams is None


@pytest.mark.asyncio
async def test_get_team_schedule_parses_broadcast_and_start_time():
    with respx.mock(base_url=espn.API_BASE_URL) as respx_mock:
        respx_mock.get("/football/nfl/teams/6/schedule").respond(
            200,
            json={
                "events": [
                    {
                        "id": "401547417",
                        "date": "2026-11-27T18:00Z",
                        "name": "Dallas Cowboys at Washington Commanders",
                        "shortName": "DAL @ WSH",
                        "seasonType": {"type": 2},
                        "competitions": [
                            {
                                "date": "2026-11-27T18:00Z",
                                "broadcasts": [{"media": {"shortName": "CBS"}}],
                            }
                        ],
                    }
                ]
            },
        )

        schedule = await espn.get_team_schedule("nfl", "6")
        assert schedule == [
            {
                "event_id": "401547417",
                "start_time": pytest.approx(1795802400.0),
                "broadcast_network": "CBS",
                "season_type": 2,
                "matchup_title": "Dallas Cowboys at Washington Commanders",
            }
        ]


@pytest.mark.asyncio
async def test_get_team_schedule_missing_broadcast_is_none():
    with respx.mock(base_url=espn.API_BASE_URL) as respx_mock:
        respx_mock.get("/football/nfl/teams/6/schedule").respond(
            200,
            json={
                "events": [
                    {
                        "id": "401547418",
                        "date": "2026-11-28T18:00Z",
                        "name": "Game",
                        "seasonType": {"type": 2},
                        "competitions": [{"date": "2026-11-28T18:00Z", "broadcasts": []}],
                    }
                ]
            },
        )

        schedule = await espn.get_team_schedule("nfl", "6")
        assert schedule[0]["broadcast_network"] is None


@pytest.mark.asyncio
async def test_get_team_schedule_degrades_gracefully_on_network_error():
    with respx.mock(base_url=espn.API_BASE_URL) as respx_mock:
        respx_mock.get(url__startswith=espn.API_BASE_URL).mock(side_effect=httpx.ConnectError("Connection refused"))

        schedule = await espn.get_team_schedule("nfl", "6")
        assert schedule is None


@pytest.mark.asyncio
async def test_get_rankings_parses_team_ids_in_order():
    with respx.mock(base_url=espn.API_BASE_URL) as respx_mock:
        respx_mock.get("/football/college-football/rankings").respond(
            200,
            json={
                "rankings": [
                    {
                        "name": "AP Top 25",
                        "ranks": [
                            {"team": {"id": "333"}},
                            {"team": {"id": "61"}},
                        ],
                    }
                ]
            },
        )

        ranked = await espn.get_rankings("college-football", "ap")
        assert ranked == ["333", "61"]


@pytest.mark.asyncio
async def test_get_rankings_degrades_gracefully_on_network_error():
    with respx.mock(base_url=espn.API_BASE_URL) as respx_mock:
        respx_mock.get(url__startswith=espn.API_BASE_URL).mock(side_effect=httpx.ConnectError("Connection refused"))

        ranked = await espn.get_rankings("college-football")
        assert ranked is None
