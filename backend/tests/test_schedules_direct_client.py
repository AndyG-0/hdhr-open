from __future__ import annotations

import pytest
import respx
from httpx import Response

from app.integrations import schedules_direct
from app.integrations.schedules_direct import SchedulesDirectError, hash_password


def test_hash_password():
    assert hash_password("secret") == "e5e9fa1ba31ecd1ae84f75caaa474f3a663f05f4"
    # Already hashed SHA-1
    assert hash_password("e5e9fa1ba31ecd1ae84f75caaa474f3a663f05f4") == "e5e9fa1ba31ecd1ae84f75caaa474f3a663f05f4"


@pytest.mark.asyncio
@respx.mock
async def test_authenticate_success():
    respx.post("https://json.schedulesdirect.org/20141201/token").mock(
        return_value=Response(
            200,
            json={"code": 0, "message": "OK", "serverID": "20141201.web.1", "token": "test-token-12345"},
        )
    )

    auth = await schedules_direct.authenticate("myuser", "mypass")
    assert auth["token"] == "test-token-12345"
    assert auth["serverID"] == "20141201.web.1"


@pytest.mark.asyncio
@respx.mock
async def test_authenticate_failure():
    respx.post("https://json.schedulesdirect.org/20141201/token").mock(
        return_value=Response(
            200,
            json={"response": "ERR", "code": 4003, "message": "Invalid username or password"},
        )
    )

    with pytest.raises(SchedulesDirectError) as exc_info:
        await schedules_direct.authenticate("baduser", "badpass")
    assert "Invalid username or password" in str(exc_info.value)
    assert exc_info.value.code == 4003


@pytest.mark.asyncio
@respx.mock
async def test_get_status():
    respx.get("https://json.schedulesdirect.org/20141201/status").mock(
        return_value=Response(
            200,
            json={
                "account": {"expires": "2027-01-01T00:00:00Z", "maxLineups": 4},
                "lineups": [
                    {"lineup": "USA-OTA-90210", "name": "Local Over the Air", "uri": "/20141201/lineups/USA-OTA-90210"}
                ],
                "systemStatus": [{"status": "Online"}],
            },
        )
    )

    status = await schedules_direct.get_status("test-token")
    assert status["account"]["expires"] == "2027-01-01T00:00:00Z"
    assert len(status["lineups"]) == 1


@pytest.mark.asyncio
@respx.mock
async def test_get_lineup():
    respx.get("https://json.schedulesdirect.org/20141201/lineups/USA-OTA-90210").mock(
        return_value=Response(
            200,
            json={
                "map": [{"stationID": "1001", "channel": "2.1"}, {"stationID": "1002", "channel": "4.1"}],
                "stations": [
                    {"stationID": "1001", "name": "KCBS-DT", "callsign": "KCBS"},
                    {"stationID": "1002", "name": "KNBC-DT", "callsign": "KNBC"},
                ],
            },
        )
    )

    lineup = await schedules_direct.get_lineup("test-token", "USA-OTA-90210")
    assert len(lineup["map"]) == 2
    assert len(lineup["stations"]) == 2


@pytest.mark.asyncio
@respx.mock
async def test_get_schedules_and_programs():
    respx.post("https://json.schedulesdirect.org/20141201/schedules").mock(
        return_value=Response(
            200,
            json=[
                {
                    "stationID": "1001",
                    "programs": [
                        {
                            "programID": "EP012345670001",
                            "airDateTime": "2026-08-18T20:00:00Z",
                            "duration": 3600,
                            "new": True,
                        }
                    ],
                }
            ],
        )
    )

    respx.post("https://json.schedulesdirect.org/20141201/programs").mock(
        return_value=Response(
            200,
            json=[
                {
                    "programID": "EP012345670001",
                    "titles": [{"title120": "Sample Show"}],
                    "episodeTitle150": "Sample Episode",
                    "descriptions": {
                        "description100": [{"description": "Short description"}],
                        "description1000": [{"description": "Full synopsis"}],
                    },
                    "originalAirDate": "2026-08-18",
                    "genres": ["Drama"],
                    "episodeInfo": {"season": 1, "number": 1},
                }
            ],
        )
    )

    schedules = await schedules_direct.get_schedules("test-token", [{"stationID": "1001", "date": ["2026-08-18"]}])
    assert len(schedules) == 1
    assert schedules[0]["stationID"] == "1001"

    programs = await schedules_direct.get_programs("test-token", ["EP012345670001"])
    assert len(programs) == 1
    assert programs[0]["titles"][0]["title120"] == "Sample Show"
