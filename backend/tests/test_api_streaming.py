from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import httpx
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


class _FakeRawResponse:
    def __init__(self, status_code: int, chunks: list[bytes]) -> None:
        self.status_code = status_code
        self._chunks = chunks
        self.aclose = AsyncMock()

    async def aiter_bytes(self, chunk_size: int):
        for chunk in self._chunks:
            yield chunk


class _FakeRawClient:
    def __init__(self, outcome: _FakeRawResponse | Exception) -> None:
        self._outcome = outcome
        self.aclose = AsyncMock()

    def build_request(self, method: str, url: str):
        return (method, url)

    async def send(self, request, stream: bool = False):
        if isinstance(self._outcome, Exception):
            raise self._outcome
        return self._outcome


def _patch_raw_client(monkeypatch, outcome: _FakeRawResponse | Exception) -> None:
    monkeypatch.setattr(streaming_api.httpx, "AsyncClient", lambda **kwargs: _FakeRawClient(outcome))


def test_stream_channel_direct_bypasses_ffmpeg_and_proxies_raw_bytes(client, tmp_db, monkeypatch):
    _configure_tuner("software")
    _patch_raw_client(monkeypatch, _FakeRawResponse(200, [b"abc", b"def"]))
    exec_mock = AsyncMock(side_effect=AssertionError("ffmpeg should not run for direct=true"))
    monkeypatch.setattr(asyncio, "create_subprocess_exec", exec_mock)

    response = client.get("/api/streaming/stream/4.1?direct=true")

    assert response.status_code == 200
    assert response.content == b"abcdef"
    assert response.headers["content-type"] == "video/mp2t"
    exec_mock.assert_not_awaited()


def test_stream_channel_direct_returns_502_when_tuner_rejects(client, tmp_db, monkeypatch):
    _configure_tuner("software")
    _patch_raw_client(monkeypatch, _FakeRawResponse(500, []))

    response = client.get("/api/streaming/stream/4.1?direct=true")

    assert response.status_code == 502
    assert "Tuner rejected" in response.json()["detail"]


def test_stream_channel_direct_returns_502_when_tuner_unreachable(client, tmp_db, monkeypatch):
    _configure_tuner("software")
    _patch_raw_client(monkeypatch, httpx.ConnectError("connection refused"))

    response = client.get("/api/streaming/stream/4.1?direct=true")

    assert response.status_code == 502
    assert "Could not reach tuner" in response.json()["detail"]
