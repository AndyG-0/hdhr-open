from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import tuner as tuner_api
from app.auth import get_current_user
from app.storage.db import save_network_integration


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(tuner_api.router)
    app.dependency_overrides[get_current_user] = lambda: {"id": "u1", "role": "member"}
    return TestClient(app)


def _configure_tuner(tmp_db):
    save_network_integration("hdhomerun", "hdhomerun", "HDHomeRun", {"tuner_host": "hdhomerun.local", "tuner_port": 80})


def test_get_info_requires_tuner_configured(client, tmp_db):
    response = client.get("/api/tuner/info")
    assert response.status_code == 404


def test_get_info_returns_discover_fields(client, tmp_db, monkeypatch):
    _configure_tuner(tmp_db)
    monkeypatch.setattr(
        tuner_api.hdhomerun_client,
        "fetch_discover",
        AsyncMock(
            return_value={
                "FriendlyName": "HDHomeRun CONNECT",
                "ModelNumber": "HDHR5-2US",
                "FirmwareVersion": "20240401",
                "TunerCount": 2,
            }
        ),
    )

    response = client.get("/api/tuner/info")

    assert response.status_code == 200
    assert response.json() == {
        "friendly_name": "HDHomeRun CONNECT",
        "model_number": "HDHR5-2US",
        "firmware_version": "20240401",
        "tuner_count": 2,
    }


def test_get_status_requires_tuner_configured(client, tmp_db):
    response = client.get("/api/tuner/status")
    assert response.status_code == 404


def test_get_status_idle_tuner(client, tmp_db, monkeypatch):
    _configure_tuner(tmp_db)
    monkeypatch.setattr(
        tuner_api.hdhomerun_client,
        "fetch_tuner_status",
        AsyncMock(
            return_value=[
                {
                    "index": 0,
                    "resource": "tuner0",
                    "in_use": False,
                    "channel_number": None,
                    "channel_name": None,
                    "target_ip": None,
                    "signal_strength_percent": None,
                    "signal_quality_percent": None,
                    "symbol_quality_percent": None,
                    "network_rate_bps": None,
                }
            ]
        ),
    )

    response = client.get("/api/tuner/status")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["index"] == 0
    assert data[0]["in_use"] is False
    assert data[0]["client"] is None
    assert data[0]["warning"] is None


def test_get_status_external_client_with_reverse_dns(client, tmp_db, monkeypatch):
    _configure_tuner(tmp_db)
    monkeypatch.setattr(
        tuner_api.hdhomerun_client,
        "fetch_tuner_status",
        AsyncMock(
            return_value=[
                {
                    "index": 0,
                    "resource": "tuner0",
                    "in_use": True,
                    "channel_number": "4.1",
                    "channel_name": "WCMH-DT",
                    "target_ip": "192.168.1.150",
                    "signal_strength_percent": 95,
                    "signal_quality_percent": 100,
                    "symbol_quality_percent": 100,
                    "network_rate_bps": 15000000,
                }
            ]
        ),
    )
    monkeypatch.setattr(
        tuner_api.hdhomerun_client,
        "resolve_hostname",
        AsyncMock(return_value="plex-server.local"),
    )

    response = client.get("/api/tuner/status")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["index"] == 0
    assert data[0]["in_use"] is True
    assert data[0]["target_ip"] == "192.168.1.150"
    assert data[0]["client"]["type"] == "external"
    assert data[0]["client"]["hostname"] == "plex-server.local"
    assert "plex-server.local" in data[0]["client"]["name"]
    assert "plex-server.local" in data[0]["warning"]["message"]
    assert data[0]["warning"]["severity"] == "warning"


def test_get_status_dvr_proxy_client(client, tmp_db, monkeypatch):
    save_network_integration(
        "hdhomerun",
        "hdhomerun",
        "HDHomeRun",
        {"tuner_host": "hdhomerun.local", "tuner_port": 80, "dvr_host": "192.168.1.200", "dvr_port": 50000},
    )
    monkeypatch.setattr(
        tuner_api.hdhomerun_client,
        "fetch_tuner_status",
        AsyncMock(
            return_value=[
                {
                    "index": 0,
                    "resource": "tuner0",
                    "in_use": True,
                    "channel_number": "4.1",
                    "channel_name": "WCMH-DT",
                    "target_ip": "192.168.1.200",
                    "signal_strength_percent": 95,
                    "signal_quality_percent": 100,
                    "symbol_quality_percent": 100,
                    "network_rate_bps": 15000000,
                }
            ]
        ),
    )
    monkeypatch.setattr(
        tuner_api.hdhomerun_client,
        "resolve_hostname",
        AsyncMock(return_value="nas-server.local"),
    )

    response = client.get("/api/tuner/status")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["client"]["type"] == "dvr_proxy"
    assert "HDHomeRun RECORD" in data[0]["client"]["name"]
    assert "192.168.1.200" in data[0]["client"]["name"]
    assert "HDHomeRun RECORD engine" in data[0]["warning"]["message"]


def test_get_status_dvr_proxy_client_with_ssh_clients(client, tmp_db, monkeypatch):
    save_network_integration(
        "hdhomerun",
        "hdhomerun",
        "HDHomeRun",
        {
            "tuner_host": "hdhomerun.local",
            "tuner_port": 80,
            "dvr_host": "192.168.1.200",
            "dvr_port": 50000,
            "dvr_ssh_enabled": True,
            "dvr_ssh_host": "192.168.1.200",
            "dvr_ssh_port": 22,
            "dvr_ssh_username": "root",
        },
    )
    monkeypatch.setattr(
        tuner_api.hdhomerun_client,
        "fetch_tuner_status",
        AsyncMock(
            return_value=[
                {
                    "index": 0,
                    "resource": "tuner0",
                    "in_use": True,
                    "channel_number": "4.1",
                    "channel_name": "WCMH-DT",
                    "target_ip": "192.168.1.200",
                    "signal_strength_percent": 95,
                    "signal_quality_percent": 100,
                    "symbol_quality_percent": 100,
                    "network_rate_bps": 15000000,
                }
            ]
        ),
    )
    monkeypatch.setattr(
        tuner_api.hdhomerun_client,
        "resolve_hostname",
        AsyncMock(return_value="nas-server.local"),
    )
    monkeypatch.setattr(
        tuner_api.hdhomerun_client,
        "fetch_dvr_ssh_clients",
        AsyncMock(return_value=[{"ip": "192.168.1.50", "hostname": "living-room-appletv.local"}]),
    )

    response = client.get("/api/tuner/status")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["client"]["type"] == "dvr_proxy"
    assert "living-room-appletv.local" in data[0]["client"]["details"]
    assert data[0]["client"]["viewers"] == [{"user_name": "living-room-appletv.local", "client_ip": "192.168.1.50"}]
    assert "living-room-appletv.local" in data[0]["warning"]["message"]


def test_get_status_dvr_proxy_client_ssh_configured_but_no_clients_keeps_plain_fallback(client, tmp_db, monkeypatch):
    save_network_integration(
        "hdhomerun",
        "hdhomerun",
        "HDHomeRun",
        {
            "tuner_host": "hdhomerun.local",
            "tuner_port": 80,
            "dvr_host": "192.168.1.200",
            "dvr_port": 50000,
            "dvr_ssh_enabled": True,
            "dvr_ssh_host": "192.168.1.200",
            "dvr_ssh_port": 22,
            "dvr_ssh_username": "root",
        },
    )
    monkeypatch.setattr(
        tuner_api.hdhomerun_client,
        "fetch_tuner_status",
        AsyncMock(
            return_value=[
                {
                    "index": 0,
                    "resource": "tuner0",
                    "in_use": True,
                    "channel_number": "4.1",
                    "channel_name": "WCMH-DT",
                    "target_ip": "192.168.1.200",
                    "signal_strength_percent": 95,
                    "signal_quality_percent": 100,
                    "symbol_quality_percent": 100,
                    "network_rate_bps": 15000000,
                }
            ]
        ),
    )
    monkeypatch.setattr(
        tuner_api.hdhomerun_client,
        "resolve_hostname",
        AsyncMock(return_value="nas-server.local"),
    )
    # SSH is configured but the fetch times out / finds nothing — must not
    # regress the plain "HDHomeRun RECORD (<ip>)" fallback.
    monkeypatch.setattr(
        tuner_api.hdhomerun_client,
        "fetch_dvr_ssh_clients",
        AsyncMock(return_value=[]),
    )

    response = client.get("/api/tuner/status")
    assert response.status_code == 200
    data = response.json()
    assert data[0]["client"]["type"] == "dvr_proxy"
    assert "HDHomeRun RECORD" in data[0]["client"]["name"]
    assert "192.168.1.200" in data[0]["client"]["name"]
    assert data[0]["client"]["viewers"] == []
    assert "HDHomeRun RECORD engine" in data[0]["warning"]["message"]


def test_get_status_scheduled_recording(client, tmp_db, monkeypatch):
    _configure_tuner(tmp_db)
    monkeypatch.setattr(
        tuner_api.hdhomerun_client,
        "fetch_tuner_status",
        AsyncMock(
            return_value=[
                {
                    "index": 0,
                    "resource": "tuner0",
                    "in_use": True,
                    "channel_number": "5.1",
                    "channel_name": "WLWT",
                    "target_ip": "192.168.1.10",
                    "signal_strength_percent": 90,
                    "signal_quality_percent": 95,
                    "symbol_quality_percent": 100,
                    "network_rate_bps": 12000000,
                }
            ]
        ),
    )

    from unittest.mock import MagicMock
    fake_capture = MagicMock()
    fake_capture.recording_id = "rec_123"
    fake_capture.scheduled_id = "sched_456"
    fake_capture.title = "Jeopardy!"
    fake_capture.channel_number = "5.1"
    fake_capture.is_temporary = False

    monkeypatch.setattr(
        tuner_api.capture_pipeline,
        "get_active_capture_by_channel",
        AsyncMock(return_value=fake_capture),
    )

    response = client.get("/api/tuner/status")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["client"]["type"] == "scheduled_recording"
    assert data[0]["client"]["is_recording"] is True
    assert data[0]["client"]["recording_id"] == "rec_123"
    assert data[0]["client"]["scheduled_id"] == "sched_456"
    assert "Jeopardy!" in data[0]["client"]["name"]
    assert data[0]["warning"]["severity"] == "danger"
    assert "Jeopardy!" in data[0]["warning"]["message"]


def test_get_status_live_watch(client, tmp_db, monkeypatch):
    _configure_tuner(tmp_db)
    monkeypatch.setattr(
        tuner_api.hdhomerun_client,
        "fetch_tuner_status",
        AsyncMock(
            return_value=[
                {
                    "index": 0,
                    "resource": "tuner0",
                    "in_use": True,
                    "channel_number": "4.1",
                    "channel_name": "WCMH",
                    "target_ip": "192.168.1.10",
                    "signal_strength_percent": 90,
                    "signal_quality_percent": 95,
                    "symbol_quality_percent": 100,
                    "network_rate_bps": 12000000,
                }
            ]
        ),
    )

    from unittest.mock import MagicMock
    fake_capture = MagicMock()
    fake_capture.recording_id = "rec_watch_1"
    fake_capture.title = "WCMH"
    fake_capture.channel_name = "WCMH"
    fake_capture.channel_number = "4.1"
    fake_capture.is_temporary = True

    fake_session = MagicMock()
    fake_session.user_name = "Andy"
    fake_session.client_ip = "192.168.1.50"
    fake_session.recording_id = "rec_watch_1"

    monkeypatch.setattr(
        tuner_api.capture_pipeline,
        "get_active_capture_by_channel",
        AsyncMock(return_value=fake_capture),
    )
    monkeypatch.setattr(
        tuner_api.watch,
        "get_watch_sessions_for_recording",
        AsyncMock(return_value=[fake_session]),
    )

    response = client.get("/api/tuner/status")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["client"]["type"] == "live_watch"
    assert data[0]["client"]["name"] == "Andy"
    assert data[0]["client"]["ip"] == "192.168.1.50"
    assert data[0]["client"]["viewers"] == [{"user_name": "Andy", "client_ip": "192.168.1.50"}]
    assert "Andy" in data[0]["warning"]["message"]
    assert data[0]["warning"]["severity"] == "warning"


def test_terminate_tuner_external(client, tmp_db, monkeypatch):
    _configure_tuner(tmp_db)
    monkeypatch.setattr(
        tuner_api.hdhomerun_client,
        "fetch_tuner_status",
        AsyncMock(
            return_value=[
                {
                    "index": 0,
                    "resource": "tuner0",
                    "in_use": True,
                    "channel_number": "4.1",
                    "channel_name": "WCMH",
                    "target_ip": "192.168.1.150",
                }
            ]
        ),
    )
    release_hw_mock = AsyncMock(return_value=True)
    monkeypatch.setattr(tuner_api.hdhomerun_client, "release_hardware_tuner", release_hw_mock)
    monkeypatch.setattr(tuner_api.capture_pipeline, "get_active_capture_by_channel", AsyncMock(return_value=None))

    response = client.post("/api/tuner/0/terminate")
    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert release_hw_mock.called


def test_terminate_tuner_scheduled_recording(client, tmp_db, monkeypatch):
    _configure_tuner(tmp_db)
    monkeypatch.setattr(
        tuner_api.hdhomerun_client,
        "fetch_tuner_status",
        AsyncMock(
            return_value=[
                {
                    "index": 0,
                    "resource": "tuner0",
                    "in_use": True,
                    "channel_number": "5.1",
                    "channel_name": "WLWT",
                    "target_ip": "192.168.1.10",
                }
            ]
        ),
    )

    from unittest.mock import MagicMock
    fake_capture = MagicMock()
    fake_capture.recording_id = "rec_sched_99"
    fake_capture.title = "News"
    fake_capture.is_temporary = False

    stop_capture_mock = AsyncMock(return_value=None)
    release_tuner_mock = AsyncMock(return_value=True)
    release_hw_mock = AsyncMock(return_value=True)

    monkeypatch.setattr(
        tuner_api.capture_pipeline, "get_active_capture_by_channel", AsyncMock(return_value=fake_capture)
    )
    monkeypatch.setattr(tuner_api.capture_pipeline, "stop_capture", stop_capture_mock)
    monkeypatch.setattr(tuner_api.tuner_allocator, "release_tuner", release_tuner_mock)
    monkeypatch.setattr(tuner_api.hdhomerun_client, "release_hardware_tuner", release_hw_mock)

    response = client.post("/api/tuner/0/terminate")
    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert stop_capture_mock.called
    assert release_tuner_mock.called
    assert release_hw_mock.called


def test_terminate_tuner_live_watch(client, tmp_db, monkeypatch):
    _configure_tuner(tmp_db)
    monkeypatch.setattr(
        tuner_api.hdhomerun_client,
        "fetch_tuner_status",
        AsyncMock(
            return_value=[
                {
                    "index": 0,
                    "resource": "tuner0",
                    "in_use": True,
                    "channel_number": "4.1",
                    "channel_name": "WCMH",
                    "target_ip": "192.168.1.10",
                }
            ]
        ),
    )

    from unittest.mock import MagicMock
    fake_capture = MagicMock()
    fake_capture.recording_id = "rec_live_77"
    fake_capture.title = "Live TV"
    fake_capture.is_temporary = True

    finalize_mock = AsyncMock(return_value=None)
    release_hw_mock = AsyncMock(return_value=True)

    monkeypatch.setattr(
        tuner_api.capture_pipeline, "get_active_capture_by_channel", AsyncMock(return_value=fake_capture)
    )
    monkeypatch.setattr(tuner_api.watch, "finalize_capture_release", finalize_mock)
    monkeypatch.setattr(tuner_api.hdhomerun_client, "release_hardware_tuner", release_hw_mock)

    response = client.post("/api/tuner/0/terminate")
    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert finalize_mock.called
    assert release_hw_mock.called
