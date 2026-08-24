from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import settings as settings_api
from app.auth import get_current_admin


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(settings_api.router)
    app.dependency_overrides[get_current_admin] = lambda: {"id": "admin", "role": "admin"}
    return TestClient(app)


def test_get_settings_returns_env_default(client, tmp_db):
    response = client.get("/api/settings")
    assert response.status_code == 200
    assert response.json() == {
        "timezone": "UTC",
        "guide_provider_priority": "xmltv,schedules_direct,hdhomerun_cloud",
        "dvr_server_priority": "builtin,hdhomerun",
    }


def test_patch_settings_persists_timezone_and_priority(client, tmp_db):
    response = client.patch(
        "/api/settings",
        json={
            "timezone": "America/Chicago",
            "guide_provider_priority": "hdhomerun_cloud,xmltv,schedules_direct",
            "dvr_server_priority": "hdhomerun,builtin",
        },
    )

    assert response.status_code == 200
    assert response.json()["timezone"] == "America/Chicago"
    assert response.json()["guide_provider_priority"] == "hdhomerun_cloud,xmltv,schedules_direct"
    assert response.json()["dvr_server_priority"] == "hdhomerun,builtin"
    get_res = client.get("/api/settings").json()
    assert get_res["timezone"] == "America/Chicago"
    assert get_res["guide_provider_priority"] == "hdhomerun_cloud,xmltv,schedules_direct"
    assert get_res["dvr_server_priority"] == "hdhomerun,builtin"


def test_patch_settings_empty_string_clears_override(client, tmp_db):
    client.patch(
        "/api/settings",
        json={
            "timezone": "America/Chicago",
            "guide_provider_priority": "hdhomerun_cloud,xmltv,schedules_direct",
            "dvr_server_priority": "hdhomerun,builtin",
        },
    )

    response = client.patch(
        "/api/settings",
        json={"timezone": "", "guide_provider_priority": "", "dvr_server_priority": ""},
    )

    assert response.status_code == 200
    assert response.json()["timezone"] == "UTC"
    assert response.json()["guide_provider_priority"] == "xmltv,schedules_direct,hdhomerun_cloud"
    assert response.json()["dvr_server_priority"] == "builtin,hdhomerun"


def test_patch_settings_rejects_unknown_key(client, tmp_db):
    response = client.patch("/api/settings", json={"nope": "x"})
    assert response.status_code == 422
