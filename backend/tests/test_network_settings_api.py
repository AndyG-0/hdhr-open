from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import network_settings as network_settings_api
from app.auth import get_current_user
from app.integrations import hdhomerun_client
from app.storage import db


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(network_settings_api.router)
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


# --- GET /api/network-settings ---------------------------------------------


def test_list_requires_login(unauthenticated_client, tmp_db):
    response = unauthenticated_client.get("/api/network-settings")
    assert response.status_code == 401


def test_list_allows_member_and_masks_secrets(member_client, tmp_db):
    db.save_network_integration(
        "schedules_direct", "schedules_direct", "Schedules Direct", {"username": "alice", "password": "secret"}
    )

    response = member_client.get("/api/network-settings")

    assert response.status_code == 200
    row = next(r for r in response.json() if r["id"] == "schedules_direct")
    assert row["settings"]["username"] == "alice"
    assert row["settings"]["has_password"] is True
    assert "password" not in row["settings"]


# --- GET /api/network-settings/{type} ---------------------------------------


def test_get_singleton_type_returns_defaults_when_unconfigured(admin_client, tmp_db):
    response = admin_client.get("/api/network-settings/xmltv")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == "xmltv"
    assert body["settings"]["url"] == ""


def test_get_singleton_type_returns_stored_row(admin_client, tmp_db):
    db.save_network_integration(
        "hdhomerun",
        "hdhomerun",
        "HDHomeRun",
        {"tuner_host": "hdhr.local", "tuner_port": 80, "dvr_host": "", "dvr_port": 50000, "epg_url": ""},
    )

    response = admin_client.get("/api/network-settings/hdhomerun")

    assert response.status_code == 200
    assert response.json()["settings"]["tuner_host"] == "hdhr.local"


def test_get_unknown_type_returns_404(admin_client, tmp_db):
    response = admin_client.get("/api/network-settings/nope")
    assert response.status_code == 404


# --- PATCH /api/network-settings/{type} -------------------------------------


def test_patch_requires_login(unauthenticated_client, tmp_db):
    response = unauthenticated_client.patch("/api/network-settings/xmltv", json={"url": "http://example.com/epg.xml"})
    assert response.status_code == 401


def test_patch_rejects_member(member_client, tmp_db):
    response = member_client.patch("/api/network-settings/xmltv", json={"url": "http://example.com/epg.xml"})
    assert response.status_code == 403


def test_patch_unknown_type_returns_404(admin_client, tmp_db):
    response = admin_client.patch("/api/network-settings/nope", json={})
    assert response.status_code == 404


def test_patch_creates_row_from_defaults_when_none_exists(admin_client, tmp_db):
    response = admin_client.patch(
        "/api/network-settings/schedules_direct", json={"username": "alice", "password": "secret"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["settings"]["username"] == "alice"
    assert body["settings"]["has_password"] is True
    stored = db.get_network_integration("schedules_direct")
    assert stored["settings"]["password"] == "secret"


def test_patch_merges_onto_existing_row(admin_client, tmp_db):
    db.save_network_integration(
        "schedules_direct", "schedules_direct", "Schedules Direct", {"username": "old", "password": "secret"}
    )

    response = admin_client.patch("/api/network-settings/schedules_direct", json={"username": "new"})

    assert response.status_code == 200
    stored = db.get_network_integration("schedules_direct")
    assert stored["settings"]["username"] == "new"
    assert stored["settings"]["password"] == "secret"


def test_get_tmdb_returns_defaults_when_unconfigured(admin_client, tmp_db):
    response = admin_client.get("/api/network-settings/tmdb")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == "tmdb"
    assert body["settings"] == {"has_api_key": False}


def test_patch_tmdb_stores_and_masks_api_key(admin_client, tmp_db):
    response = admin_client.patch("/api/network-settings/tmdb", json={"api_key": "shh-secret"})

    assert response.status_code == 200
    body = response.json()
    assert body["settings"] == {"has_api_key": True}
    stored = db.get_network_integration("tmdb")
    assert stored["settings"]["api_key"] == "shh-secret"


# --- POST /api/network-settings/hdhomerun/test-{tuner,dvr}-connection -------


def test_hdhomerun_tuner_test_connection_requires_login(unauthenticated_client, tmp_db):
    response = unauthenticated_client.post("/api/network-settings/hdhomerun/test-tuner-connection", json={})
    assert response.status_code == 401


def test_hdhomerun_tuner_test_connection_requires_admin(member_client, tmp_db):
    response = member_client.post("/api/network-settings/hdhomerun/test-tuner-connection", json={})
    assert response.status_code == 403


def test_hdhomerun_tuner_test_connection_ok(admin_client, tmp_db, monkeypatch):
    db.save_network_integration(
        "hdhomerun",
        "hdhomerun",
        "HDHomeRun",
        {"tuner_host": "hdhr.local", "tuner_port": 80, "dvr_host": "", "dvr_port": 50000, "epg_url": ""},
    )

    async def fake(settings):
        assert settings["tuner_host"] == "hdhr.local"
        return "HDHomeRun FLEX"

    monkeypatch.setattr(hdhomerun_client, "test_tuner_connection", fake)

    response = admin_client.post("/api/network-settings/hdhomerun/test-tuner-connection", json={})

    assert response.json() == {"ok": True, "detail": "HDHomeRun FLEX", "error": None}


def test_hdhomerun_tuner_test_connection_reports_failure(admin_client, tmp_db, monkeypatch):
    async def fake(settings):
        raise hdhomerun_client.HDHomeRunError("unreachable")

    monkeypatch.setattr(hdhomerun_client, "test_tuner_connection", fake)

    response = admin_client.post("/api/network-settings/hdhomerun/test-tuner-connection", json={})

    assert response.status_code == 200
    assert response.json() == {"ok": False, "detail": None, "error": "unreachable"}


def test_hdhomerun_tuner_test_connection_uses_payload_override_onto_saved_settings(admin_client, tmp_db, monkeypatch):
    db.save_network_integration(
        "hdhomerun",
        "hdhomerun",
        "HDHomeRun",
        {"tuner_host": "old.local", "tuner_port": 80, "dvr_host": "", "dvr_port": 50000, "epg_url": ""},
    )
    captured: dict[str, object] = {}

    async def fake(settings):
        captured.update(settings)
        return "ok"

    monkeypatch.setattr(hdhomerun_client, "test_tuner_connection", fake)

    response = admin_client.post(
        "/api/network-settings/hdhomerun/test-tuner-connection", json={"tuner_host": "candidate.local"}
    )

    assert response.status_code == 200
    assert captured["tuner_host"] == "candidate.local"
    assert captured["tuner_port"] == 80


def test_hdhomerun_dvr_test_connection_requires_admin(member_client, tmp_db):
    response = member_client.post("/api/network-settings/hdhomerun/test-dvr-connection", json={})
    assert response.status_code == 403


def test_hdhomerun_dvr_test_connection_ok(admin_client, tmp_db, monkeypatch):
    async def fake(settings):
        return "DVR v1.2.3"

    monkeypatch.setattr(hdhomerun_client, "test_dvr_connection", fake)

    response = admin_client.post("/api/network-settings/hdhomerun/test-dvr-connection", json={})

    assert response.json() == {"ok": True, "detail": "DVR v1.2.3", "error": None}


def test_hdhomerun_dvr_test_connection_reports_failure(admin_client, tmp_db, monkeypatch):
    async def fake(settings):
        raise hdhomerun_client.HDHomeRunError("unreachable")

    monkeypatch.setattr(hdhomerun_client, "test_dvr_connection", fake)

    response = admin_client.post("/api/network-settings/hdhomerun/test-dvr-connection", json={})

    assert response.status_code == 200
    assert response.json() == {"ok": False, "detail": None, "error": "unreachable"}
