from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import sports as sports_api
from app.auth import get_current_user
from app.storage import db


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(sports_api.router)
    return app


@pytest.fixture
def admin_client():
    app = _app()
    app.dependency_overrides[get_current_user] = lambda: {"id": "admin", "role": "admin"}
    return TestClient(app)


@pytest.fixture
def member_client():
    app = _app()
    app.dependency_overrides[get_current_user] = lambda: {"id": "member", "role": "member"}
    return TestClient(app)


@pytest.fixture
def unauthenticated_client():
    return TestClient(_app())


@pytest.fixture(autouse=True)
def _mock_sync(monkeypatch):
    """Every mutating route fires a background sync - mock it out so tests
    don't depend on ESPN network access, and don't race the request."""
    mock = AsyncMock()
    monkeypatch.setattr(sports_api, "sync_sports_autorecord", lambda: mock())
    return mock


def test_list_favorites_requires_login(unauthenticated_client, tmp_db):
    response = unauthenticated_client.get("/api/sports/favorites")
    assert response.status_code == 401


def test_create_favorite_requires_admin(member_client, tmp_db):
    response = member_client.post(
        "/api/sports/favorites", json={"league": "nfl", "espn_team_id": "6", "team_display_name": "Dallas Cowboys"}
    )
    assert response.status_code == 403


def test_create_favorite_rejects_unknown_league(admin_client, tmp_db):
    response = admin_client.post("/api/sports/favorites", json={"league": "not-a-league", "espn_team_id": "6"})
    assert response.status_code == 422


def test_create_and_list_favorite(admin_client, tmp_db):
    response = admin_client.post(
        "/api/sports/favorites", json={"league": "nfl", "espn_team_id": "6", "team_display_name": "Dallas Cowboys"}
    )
    assert response.status_code == 200
    favorite = response.json()
    assert favorite["league"] == "nfl"
    assert favorite["enabled"] is True

    listed = admin_client.get("/api/sports/favorites").json()["favorites"]
    assert len(listed) == 1
    assert listed[0]["id"] == favorite["id"]


def test_update_favorite_toggles_enabled(admin_client, tmp_db):
    favorite = admin_client.post("/api/sports/favorites", json={"league": "nfl", "espn_team_id": "6"}).json()

    response = admin_client.patch(f"/api/sports/favorites/{favorite['id']}", json={"enabled": False})
    assert response.status_code == 200
    assert response.json()["enabled"] == 0


def test_update_missing_favorite_404s(admin_client, tmp_db):
    response = admin_client.patch("/api/sports/favorites/not-real", json={"enabled": False})
    assert response.status_code == 404


def test_delete_favorite_cleans_up_tracked_events_and_rule(admin_client, tmp_db):
    favorite = admin_client.post("/api/sports/favorites", json={"league": "nfl", "espn_team_id": "6"}).json()

    db.create_recording_rule(
        {
            "id": "rule_1",
            "provider": "builtin",
            "type": "single",
            "title": "Dallas Cowboys at Arizona Cardinals",
            "series_match_key": "1234567890",
            "channel_id": "7.1",
        }
    )
    db.upsert_tracked_event(
        {
            "espn_event_id": "evt_1",
            "favorite_id": favorite["id"],
            "recording_rule_id": "rule_1",
            "league": "nfl",
            "start_ts": 1234567890.0,
            "network_name": "CBS",
            "title_resolved": True,
        }
    )

    response = admin_client.delete(f"/api/sports/favorites/{favorite['id']}")
    assert response.status_code == 204
    assert db.get_recording_rule("rule_1") is None
    assert db.list_tracked_events() == []
    assert db.get_sports_favorite(favorite["id"]) is None


def test_unresolved_networks_grouped(admin_client, tmp_db):
    db.create_sports_favorite({"id": "fav_1", "league": "nfl", "espn_team_id": "6"})
    db.upsert_tracked_event(
        {
            "espn_event_id": "evt_1",
            "favorite_id": "fav_1",
            "recording_rule_id": None,
            "league": "nfl",
            "start_ts": 1234567890.0,
            "network_name": "FOX",
        }
    )
    db.upsert_tracked_event(
        {
            "espn_event_id": "evt_2",
            "favorite_id": "fav_1",
            "recording_rule_id": None,
            "league": "nfl",
            "start_ts": 1234567891.0,
            "network_name": "FOX",
        }
    )

    response = admin_client.get("/api/sports/unresolved-networks")
    unresolved = response.json()["unresolved_networks"]
    assert unresolved == [{"network_name": "FOX", "upcoming_count": 2}]


def test_save_network_map_rejects_unknown_channel(admin_client, tmp_db):
    response = admin_client.put("/api/sports/network-map/CBS", json={"channel_id": "not-a-channel"})
    assert response.status_code == 422


def test_save_and_list_network_map(admin_client, tmp_db):
    channel_id = uuid.uuid4().hex
    db.upsert_channel(channel_id, "7.1", "KCBS", True)

    response = admin_client.put("/api/sports/network-map/CBS", json={"channel_id": channel_id})
    assert response.status_code == 200

    listed = admin_client.get("/api/sports/network-map").json()["network_map"]
    assert listed == [
        {"network_name": "CBS", "channel_id": channel_id, "channel_number": "7.1", "channel_name": "KCBS"}
    ]


def test_delete_network_map_entry(admin_client, tmp_db):
    channel_id = uuid.uuid4().hex
    db.upsert_channel(channel_id, "7.1", "KCBS", True)
    db.save_network_channel_map_entry("CBS", channel_id)

    response = admin_client.delete("/api/sports/network-map/CBS")
    assert response.status_code == 204
    assert db.list_network_channel_map() == []
