from __future__ import annotations

import pytest
import respx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import Response

from app.api import guide as guide_api
from app.auth import get_current_admin, get_current_user
from app.storage import db


@pytest.fixture
def admin_client():
    app = FastAPI()
    app.include_router(guide_api.router)
    app.dependency_overrides[get_current_user] = lambda: {"id": "u1", "role": "admin"}
    app.dependency_overrides[get_current_admin] = lambda: {"id": "u1", "role": "admin"}
    return TestClient(app)


def test_channel_settings_sd_mapping(admin_client, tmp_db):
    # Setup channel
    ch_id = "test-ch-sd"
    db.upsert_channel(ch_id, "7.1", "ABC", True)

    # 1. Update channel with schedules_direct guide_provider and sd_station_id
    res = admin_client.patch(
        f"/api/guide/channels/{ch_id}",
        json={
            "guide_provider": "schedules_direct",
            "sd_station_id": "1007",
            "sd_lineup_id": "USA-OTA-90210",
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["guide_provider"] == "schedules_direct"
    assert data["sd_station_id"] == "1007"
    assert data["sd_lineup_id"] == "USA-OTA-90210"

    # 2. Verify in GET /api/guide/channels/settings
    get_res = admin_client.get("/api/guide/channels/settings")
    assert get_res.status_code == 200
    ch_settings = next((c for c in get_res.json() if c["id"] == ch_id), None)
    assert ch_settings is not None
    assert ch_settings["guide_provider"] == "schedules_direct"
    assert ch_settings["sd_station_id"] == "1007"
    assert ch_settings["sd_lineup_id"] == "USA-OTA-90210"

    # 3. Clear sd_station_id
    clear_res = admin_client.patch(
        f"/api/guide/channels/{ch_id}",
        json={"sd_station_id": "", "sd_lineup_id": ""},
    )
    assert clear_res.status_code == 200
    assert clear_res.json()["sd_station_id"] is None
    assert clear_res.json()["sd_lineup_id"] is None


@respx.mock
def test_get_schedules_direct_stations(admin_client, tmp_db):
    db.save_network_integration(
        "schedules_direct", "schedules_direct", "Schedules Direct", {"username": "u1", "password": "p1"}
    )

    respx.post("https://json.schedulesdirect.org/20141201/token").mock(
        return_value=Response(200, json={"code": 0, "token": "token-1"})
    )
    respx.get("https://json.schedulesdirect.org/20141201/status").mock(
        return_value=Response(
            200,
            json={
                "lineups": [{"lineup": "USA-OTA-90210", "name": "Local OTA", "uri": "/lineup"}],
            },
        )
    )
    respx.get("https://json.schedulesdirect.org/20141201/lineups/USA-OTA-90210").mock(
        return_value=Response(
            200,
            json={
                "map": [{"stationID": "1001", "channel": "2.1"}],
                "stations": [{"stationID": "1001", "name": "KCBS-DT", "callsign": "KCBS"}],
            },
        )
    )

    res = admin_client.get("/api/guide/schedules-direct-stations")
    assert res.status_code == 200
    stations = res.json()
    assert len(stations) == 1
    assert stations[0]["station_id"] == "1001"
    assert stations[0]["callsign"] == "KCBS"
    assert stations[0]["channel_number"] == "2.1"
