from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import watch as watch_api
from app.auth import get_current_user
from app.dvr.builtin import watch
from app.dvr.builtin.capture import capture_pipeline
from app.dvr.builtin.engine import DVREngine
from app.dvr.builtin.tuner_allocator import tuner_allocator
from app.integrations import hdhomerun_client
from app.storage import db


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(watch_api.router)
    app.dependency_overrides[get_current_user] = lambda: {"id": "u1", "role": "member"}
    return TestClient(app)


@pytest.fixture(autouse=True)
def _reset_singletons():
    """capture_pipeline and tuner_allocator are process-wide singletons (same
    ones the real app uses), so tests must not leak active state between
    each other."""
    capture_pipeline._active_captures.clear()
    capture_pipeline._channel_index.clear()
    tuner_allocator._channel_owners.clear()
    tuner_allocator._token_channel.clear()
    watch._sessions.clear()
    yield
    capture_pipeline._active_captures.clear()
    capture_pipeline._channel_index.clear()
    tuner_allocator._channel_owners.clear()
    tuner_allocator._token_channel.clear()
    watch._sessions.clear()


TUNER_SETTINGS = {"tuner_host": "hdhomerun.local", "tuner_port": 80}
TUNERS_FREE = [{"in_use": False}, {"in_use": False}]
TUNERS_BUSY = [{"in_use": True}, {"in_use": True}]


def _mock_process() -> MagicMock:
    proc = MagicMock()
    proc.returncode = None
    proc.terminate = MagicMock()
    proc.wait = AsyncMock(return_value=0)
    proc.stderr = MagicMock()
    proc.stderr.read = AsyncMock(return_value=b"")
    return proc


@pytest.fixture
def watch_env(tmp_db, tmp_path, monkeypatch):
    """A tuner-configured household with one free (mocked) hardware tuner
    and a mocked ffmpeg, so capture_pipeline.start_capture runs its real
    logic (writes a DB row, tracks an ActiveCapture) without touching the
    network or spawning a real process."""
    db.save_network_integration("hdhomerun", "hdhomerun", "HDHomeRun", TUNER_SETTINGS)
    monkeypatch.setattr(capture_pipeline, "_ensure_recordings_dir", lambda: tmp_path)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", AsyncMock(side_effect=lambda *a, **kw: _mock_process()))
    monkeypatch.setattr(hdhomerun_client, "fetch_discover", AsyncMock(return_value={"TunerCount": 2}))
    monkeypatch.setattr(hdhomerun_client, "fetch_tuner_status", AsyncMock(return_value=TUNERS_FREE))
    return tmp_path


def test_start_watch_success(client, watch_env):
    response = client.post("/api/watch/4.1/start")
    assert response.status_code == 200
    body = response.json()
    assert body["recording_id"]
    assert body["session_id"]
    assert body["play_url"]
    assert body["is_dvr_file"] is True

    row = db.get_recording(body["recording_id"])
    assert row is not None
    assert row["is_temporary"] == 1
    assert row["status"] == "recording"


def test_start_watch_shares_capture_across_sessions(client, watch_env):
    """A second viewer opening the same channel attaches to the existing
    capture instead of starting a second tuner/ffmpeg."""
    first = client.post("/api/watch/4.1/start").json()
    second = client.post("/api/watch/4.1/start").json()

    assert first["recording_id"] == second["recording_id"]
    assert first["session_id"] != second["session_id"]
    assert len(capture_pipeline._active_captures) == 1
    assert tuner_allocator._channel_owners.get("4.1") == {first["session_id"], second["session_id"]}


@pytest.mark.asyncio
async def test_start_watch_concurrent_requests_share_one_capture(watch_env):
    """Two near-simultaneous start_watch calls for the same channel (e.g. two
    clients tuning in at once) must not race into spawning two independent
    ffmpeg/tuner captures - they should converge on exactly one, the same way
    a second sequential viewer attaches to an already-running capture."""
    results = await asyncio.gather(
        watch.start_watch("4.1", TUNER_SETTINGS),
        watch.start_watch("4.1", TUNER_SETTINGS),
    )

    assert all(r is not None for r in results)
    recording_ids = {r["recording_id"] for r in results}
    session_ids = {r["session_id"] for r in results}
    assert len(recording_ids) == 1
    assert len(session_ids) == 2
    # Exactly one capture (and thus one writer ffmpeg / one tuner grab) was
    # started for the channel - pre-fix, the unguarded check-then-act race let
    # both concurrent calls see "nothing running" and each start their own
    # capture, leaving two entries here with the second silently clobbering
    # the first in _channel_index.
    assert len(capture_pipeline._active_captures) == 1
    assert tuner_allocator._channel_owners.get("4.1") == session_ids


def test_start_watch_no_free_tuner(client, watch_env, monkeypatch):
    monkeypatch.setattr(hdhomerun_client, "fetch_tuner_status", AsyncMock(return_value=TUNERS_BUSY))

    response = client.post("/api/watch/4.1/start")
    assert response.status_code == 200
    assert response.json() == {"recording_id": None, "session_id": None}


def test_start_watch_tuner_not_configured(client, tmp_db):
    response = client.post("/api/watch/4.1/start")
    assert response.status_code == 404


def test_heartbeat_watch(client, watch_env):
    body = client.post("/api/watch/4.1/start").json()
    session_id = body["session_id"]
    recording_id = body["recording_id"]

    # last_heartbeat_at isn't set at capture creation, only by heartbeats.
    assert db.get_recording(recording_id)["last_heartbeat_at"] is None
    response = client.post(f"/api/watch/{session_id}/heartbeat")
    assert response.status_code == 204
    assert db.get_recording(recording_id)["last_heartbeat_at"] is not None


def test_heartbeat_watch_not_found(client, watch_env):
    response = client.post("/api/watch/does-not-exist/heartbeat")
    assert response.status_code == 404


def test_stop_watch_deletes_temporary_recording(client, watch_env):
    body = client.post("/api/watch/4.1/start").json()
    session_id = body["session_id"]
    recording_id = body["recording_id"]
    capture = capture_pipeline._active_captures[recording_id]
    capture.file_path.write_bytes(b"MPEG-TS data" * 10000)

    response = client.post(f"/api/watch/{session_id}/stop")
    assert response.status_code == 204
    assert db.get_recording(recording_id) is None
    assert not capture.file_path.exists()


def test_stop_watch_leaves_capture_running_for_other_viewers(client, watch_env):
    first = client.post("/api/watch/4.1/start").json()
    second = client.post("/api/watch/4.1/start").json()
    recording_id = first["recording_id"]
    capture = capture_pipeline._active_captures[recording_id]
    capture.file_path.write_bytes(b"MPEG-TS data" * 10000)

    response = client.post(f"/api/watch/{first['session_id']}/stop")
    assert response.status_code == 204

    # Second viewer is still attached, so the capture survives.
    assert db.get_recording(recording_id) is not None
    assert recording_id in capture_pipeline._active_captures
    assert tuner_allocator._channel_owners.get("4.1") == {second["session_id"]}

    response = client.post(f"/api/watch/{second['session_id']}/stop")
    assert response.status_code == 204
    assert db.get_recording(recording_id) is None
    assert "4.1" not in tuner_allocator._channel_owners


def test_stop_watch_noop_once_promoted(client, watch_env):
    body = client.post("/api/watch/4.1/start").json()
    session_id = body["session_id"]
    recording_id = body["recording_id"]
    promote_res = client.post(f"/api/watch/{session_id}/promote", json={"title": "Kept Show"})
    assert promote_res.status_code == 200

    response = client.post(f"/api/watch/{session_id}/stop")
    assert response.status_code == 204

    row = db.get_recording(recording_id)
    assert row is not None
    assert row["is_temporary"] == 0
    assert row["status"] == "recording"
    # The tuner stays reserved for the now-permanent recording even after
    # its originating viewer session stops.
    assert recording_id in tuner_allocator._token_channel


def test_promote_watch(client, watch_env):
    body = client.post("/api/watch/4.1/start").json()
    session_id = body["session_id"]
    recording_id = body["recording_id"]

    response = client.post(
        f"/api/watch/{session_id}/promote",
        json={"title": "The Nightly Show", "episode_title": "Season Finale"},
    )
    assert response.status_code == 200
    resp_body = response.json()
    assert resp_body["title"] == "The Nightly Show"
    assert resp_body["episode_title"] == "Season Finale"

    row = db.get_recording(recording_id)
    assert row["is_temporary"] == 0
    assert row["title"] == "The Nightly Show"

    capture = capture_pipeline._active_captures[recording_id]
    assert capture.title == "The Nightly Show"


def test_promote_watch_not_found(client, watch_env):
    response = client.post("/api/watch/does-not-exist/promote", json={})
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_reap_stale_watches_via_engine_tick(tmp_db, tmp_path, monkeypatch):
    db.save_network_integration("hdhomerun", "hdhomerun", "HDHomeRun", TUNER_SETTINGS)
    monkeypatch.setattr(capture_pipeline, "_ensure_recordings_dir", lambda: tmp_path)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", AsyncMock(side_effect=lambda *a, **kw: _mock_process()))
    monkeypatch.setattr(hdhomerun_client, "fetch_discover", AsyncMock(return_value={"TunerCount": 2}))
    monkeypatch.setattr(hdhomerun_client, "fetch_tuner_status", AsyncMock(return_value=TUNERS_FREE))

    result = await watch.start_watch("4.1", TUNER_SETTINGS)
    assert result is not None
    session_id = result["session_id"]
    recording_id = result["recording_id"]

    # Simulate an abandoned session: the client stopped heartbeating well
    # past WATCH_HEARTBEAT_TIMEOUT_SECONDS ago.
    watch._sessions[session_id].last_heartbeat_at = time.time() - watch.WATCH_HEARTBEAT_TIMEOUT_SECONDS - 30

    capture_pipeline._active_captures[recording_id].file_path.write_bytes(b"MPEG-TS data" * 10000)

    engine = DVREngine()
    await engine.tick()

    assert db.get_recording(recording_id) is None
    assert session_id not in tuner_allocator.active_recording_ids()
    assert session_id not in watch._sessions
