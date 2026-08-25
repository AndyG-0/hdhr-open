from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import hwaccel
from app.api import streaming as streaming_api
from app.auth import get_current_user
from app.storage import db
from app.subprocess_streaming import FFMPEG_NOT_FOUND_DETAIL


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(streaming_api.router)
    app.dependency_overrides[get_current_user] = lambda: {"id": "u1", "role": "member"}
    return TestClient(app)


def _configure_tuner(hwaccel_preset: str = "software") -> None:
    db.save_network_integration(
        "hdhomerun", "hdhomerun", "HDHomeRun", {"tuner_host": "hdhomerun.local", "hwaccel": hwaccel_preset}
    )


def _fake_ffmpeg_process(*, returncode: int | None, stderr_chunks: list[bytes]) -> MagicMock:
    proc = MagicMock()
    proc.returncode = returncode
    proc.terminate = MagicMock()
    proc.kill = MagicMock()
    proc.wait = AsyncMock(return_value=returncode)
    proc.stdout = MagicMock()
    proc.stdout.read = AsyncMock(return_value=b"")
    proc.stderr = MagicMock()
    proc.stderr.read = AsyncMock(side_effect=[*stderr_chunks, b""])
    return proc


def test_stream_channel_immediate_exit_returns_502_with_ffmpeg_reason(client, tmp_db, monkeypatch):
    _configure_tuner("software")
    proc = _fake_ffmpeg_process(returncode=1, stderr_chunks=[b"no soup for you"])
    monkeypatch.setattr(asyncio, "create_subprocess_exec", AsyncMock(return_value=proc))

    response = client.get("/api/streaming/stream/4.1")

    assert response.status_code == 502
    detail = response.json()["detail"]
    assert "Could not start streaming channel 4.1" in detail
    assert "exited with code 1" in detail
    assert "no soup for you" in detail


def test_stream_channel_missing_ffmpeg_binary_returns_unified_503(client, tmp_db, monkeypatch):
    _configure_tuner("software")
    monkeypatch.setattr(asyncio, "create_subprocess_exec", AsyncMock(side_effect=FileNotFoundError()))

    response = client.get("/api/streaming/stream/4.1")

    assert response.status_code == 503
    assert response.json()["detail"] == FFMPEG_NOT_FOUND_DETAIL


def test_stream_channel_hardware_preset_failure_invokes_probe(client, tmp_db, monkeypatch):
    _configure_tuner("videotoolbox")
    proc = _fake_ffmpeg_process(returncode=1, stderr_chunks=[b"gpu init failed"])
    monkeypatch.setattr(asyncio, "create_subprocess_exec", AsyncMock(return_value=proc))

    mock_probe = AsyncMock(
        return_value={"ok": False, "command": "ffmpeg -probe", "exit_code": 1, "output": "gpu also broken"}
    )
    monkeypatch.setattr(hwaccel, "probe_transcode", mock_probe)

    response = client.get("/api/streaming/stream/4.1")

    assert response.status_code == 502
    detail = response.json()["detail"]
    assert "A test transcode with these same settings also failed" in detail
    mock_probe.assert_awaited_once()


def test_stream_channel_software_preset_failure_does_not_invoke_probe(client, tmp_db, monkeypatch):
    _configure_tuner("software")
    proc = _fake_ffmpeg_process(returncode=1, stderr_chunks=[b"tuner busy"])
    monkeypatch.setattr(asyncio, "create_subprocess_exec", AsyncMock(return_value=proc))

    mock_probe = AsyncMock()
    monkeypatch.setattr(hwaccel, "probe_transcode", mock_probe)

    response = client.get("/api/streaming/stream/4.1")

    assert response.status_code == 502
    mock_probe.assert_not_awaited()
