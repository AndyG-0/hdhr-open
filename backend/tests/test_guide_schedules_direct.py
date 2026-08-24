from __future__ import annotations

import pytest
import respx
from httpx import Response

from app.guide import schedules_direct as sd_guide
from app.storage import db


@pytest.mark.asyncio
@respx.mock
async def test_refresh_schedules_direct_guide(tmp_db):
    # Setup channel in DB
    channel_id = "c100"
    db.upsert_channel(channel_id, "2.1", "CBS", True)

    # Save network settings
    db.save_network_integration(
        "schedules_direct", "schedules_direct", "Schedules Direct", {"username": "user1", "password": "pass1"}
    )

    # Mock token
    respx.post("https://json.schedulesdirect.org/20141201/token").mock(
        return_value=Response(200, json={"code": 0, "token": "test-sd-token"})
    )

    # Mock status
    respx.get("https://json.schedulesdirect.org/20141201/status").mock(
        return_value=Response(
            200,
            json={
                "account": {"expires": "2027-01-01T00:00:00Z"},
                "lineups": [{"lineup": "USA-OTA-90210", "name": "Local OTA", "uri": "/20141201/lineups/USA-OTA-90210"}],
            },
        )
    )

    # Mock lineup
    respx.get("https://json.schedulesdirect.org/20141201/lineups/USA-OTA-90210").mock(
        return_value=Response(
            200,
            json={
                "map": [{"stationID": "1001", "channel": "2.1"}],
                "stations": [{"stationID": "1001", "name": "KCBS-DT", "callsign": "KCBS"}],
            },
        )
    )

    # Mock schedules
    sched_route = respx.post("https://json.schedulesdirect.org/20141201/schedules").mock(
        return_value=Response(
            200,
            json=[
                {
                    "stationID": "1001",
                    "programs": [
                        {
                            "programID": "EP0001",
                            "airDateTime": "2026-08-18T20:00:00Z",
                            "duration": 3600,
                            "new": True,
                        }
                    ],
                }
            ],
        )
    )

    # Mock programs
    respx.post("https://json.schedulesdirect.org/20141201/programs").mock(
        return_value=Response(
            200,
            json=[
                {
                    "programID": "EP0001",
                    "titles": [{"title120": "Evening News"}],
                    "episodeTitle150": "Daily Highlights",
                    "descriptions": {"description1000": [{"description": "The latest national news."}]},
                    "genres": ["News"],
                    "originalAirDate": "2026-08-18",
                }
            ],
        )
    )

    await sd_guide.refresh_schedules_direct_guide()

    # Verify request payload included yesterday (UTC) as starting date
    assert sched_route.call_count == 1
    import json
    sched_req_body = json.loads(sched_route.calls[0].request.content.decode("utf-8"))
    assert len(sched_req_body) == 1
    assert len(sched_req_body[0]["date"]) == sd_guide.QUERY_DAYS + 1

    # Verify channel was auto-mapped
    sd_map = db.get_sd_station_map(channel_id)
    assert sd_map is not None
    assert sd_map["station_id"] == "1001"
    assert sd_map["lineup_id"] == "USA-OTA-90210"

    # Verify guide programs were written
    programs = db.list_guide_programs([channel_id], 0, 2000000000)
    assert len(programs) == 1
    prog = programs[0]
    assert prog["source_provider"] == "schedules_direct"
    assert prog["title"] == "Evening News"
    assert prog["episode_title"] == "Daily Highlights"
    assert prog["synopsis"] == "The latest national news."
    assert prog["is_new"] == 1
    assert prog["category"] == "News"

    # Verify provider state
    state = db.get_guide_provider_state("schedules_direct")
    assert state is not None
    assert state["last_refreshed_at"] is not None
