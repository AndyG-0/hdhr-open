from __future__ import annotations

import pytest
import respx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import Response

from app.api import network_settings as net_api
from app.auth import get_current_admin, get_current_user
from app.storage import db


@pytest.fixture
def admin_client():
    app = FastAPI()
    app.include_router(net_api.router)
    app.dependency_overrides[get_current_user] = lambda: {"id": "u1", "role": "admin"}
    app.dependency_overrides[get_current_admin] = lambda: {"id": "u1", "role": "admin"}
    return TestClient(app)


@respx.mock
def test_schedules_direct_test_connection_success(admin_client, tmp_db):
    respx.post("https://json.schedulesdirect.org/20141201/token").mock(
        return_value=Response(200, json={"code": 0, "token": "test-token"})
    )
    respx.get("https://json.schedulesdirect.org/20141201/status").mock(
        return_value=Response(
            200,
            json={
                "account": {"expires": "2027-05-01T00:00:00Z", "maxLineups": 4},
                "lineups": [{"lineup": "USA-OTA-90210", "name": "Local OTA", "uri": "/lineups/USA-OTA-90210"}],
            },
        )
    )

    res = admin_client.post(
        "/api/network-settings/schedules-direct/test-connection",
        json={"username": "valid_user", "password": "valid_password"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert data["error"] is None
    assert data["detail"]["expires"] == "2027-05-01T00:00:00Z"
    assert len(data["detail"]["lineups"]) == 1


@respx.mock
def test_schedules_direct_test_connection_failure(admin_client, tmp_db):
    respx.post("https://json.schedulesdirect.org/20141201/token").mock(
        return_value=Response(200, json={"response": "ERR", "code": 4003, "message": "Invalid credentials"})
    )

    res = admin_client.post(
        "/api/network-settings/schedules-direct/test-connection",
        json={"username": "bad_user", "password": "bad_password"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is False
    assert "Invalid credentials" in data["error"]


@respx.mock
def test_schedules_direct_lineup_management(admin_client, tmp_db):
    db.save_network_integration(
        "schedules_direct", "schedules_direct", "Schedules Direct", {"username": "user1", "password": "pw1"}
    )

    respx.post("https://json.schedulesdirect.org/20141201/token").mock(
        return_value=Response(200, json={"code": 0, "token": "token-xyz"})
    )
    respx.get("https://json.schedulesdirect.org/20141201/status").mock(
        return_value=Response(
            200,
            json={
                "account": {"expires": "2027-01-01T00:00:00Z"},
                "lineups": [{"lineup": "USA-OTA-90210", "name": "Local OTA", "uri": "/lineup"}],
            },
        )
    )
    respx.get("https://json.schedulesdirect.org/20141201/headends").mock(
        return_value=Response(
            200,
            json=[
                {
                    "headend": "90210",
                    "lineups": [{"lineup": "USA-OTA-90210", "name": "Broadcast"}],
                }
            ],
        )
    )
    respx.put("https://json.schedulesdirect.org/20141201/lineups/USA-OTA-90210").mock(
        return_value=Response(200, json={"code": 0, "message": "Added lineup"})
    )
    respx.delete("https://json.schedulesdirect.org/20141201/lineups/USA-OTA-90210").mock(
        return_value=Response(200, json={"code": 0, "message": "Deleted lineup"})
    )

    # 1. List lineups
    lineups_res = admin_client.get("/api/network-settings/schedules-direct/lineups")
    assert lineups_res.status_code == 200
    assert len(lineups_res.json()) == 1

    # 2. List headends
    headends_res = admin_client.get("/api/network-settings/schedules-direct/headends?postal_code=90210")
    assert headends_res.status_code == 200
    assert len(headends_res.json()) == 1

    # 3. Add lineup
    add_res = admin_client.post("/api/network-settings/schedules-direct/lineups/USA-OTA-90210")
    assert add_res.status_code == 200

    # 4. Delete lineup
    del_res = admin_client.delete("/api/network-settings/schedules-direct/lineups/USA-OTA-90210")
    assert del_res.status_code == 200
