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
