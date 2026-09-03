from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import hls_streaming
from app.api import hls as hls_api
from app.auth import get_current_user


@pytest.fixture(autouse=True)
def _reset_sessions():
    """Same process-wide singleton _reset_sessions guards in
    test_hls_streaming.py - required here too since this file registers
    sessions directly into hls_streaming._sessions."""
    hls_streaming._sessions.clear()
    yield
    hls_streaming._sessions.clear()


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(hls_api.router)
    app.dependency_overrides[get_current_user] = lambda: {"id": "u1", "role": "member"}
    return TestClient(app)


@pytest.fixture
def unauthenticated_client():
    app = FastAPI()
    app.include_router(hls_api.router)
    return TestClient(app)


def _register_session(tmp_path, *, cast_token: str | None = None) -> hls_streaming.HLSSession:
    tmp_dir = tmp_path / "sess"
    tmp_dir.mkdir()
    hls_streaming.playlist_path(tmp_dir).write_bytes(b"#EXTM3U\n#EXTINF:2.0,\nsegment00000.ts\n")
    (tmp_dir / "segment00000.ts").write_bytes(b"tsdata")
    now = time.time()
    session = hls_streaming.HLSSession(
        session_id="sess1",
        process=MagicMock(),
        tmp_dir=tmp_dir,
        created_at=now,
        last_request_at=now,
        label="test",
        cast_token=cast_token,
    )
    hls_streaming._sessions[session.session_id] = session
    return session


# --- existing cookie/bearer-authenticated routes - unaffected by the new
# per-route dependencies (moved off the router-level `dependencies=`) ------


def test_get_playlist_requires_auth(unauthenticated_client, tmp_path):
    _register_session(tmp_path)
    response = unauthenticated_client.get("/api/hls/sess1/playlist.m3u8")
    assert response.status_code == 401


def test_get_playlist_authenticated_returns_playlist(client, tmp_path):
    _register_session(tmp_path)
    response = client.get("/api/hls/sess1/playlist.m3u8")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/vnd.apple.mpegurl"


def test_get_segment_authenticated_returns_segment(client, tmp_path):
    _register_session(tmp_path)
    response = client.get("/api/hls/sess1/segment00000.ts")
    assert response.status_code == 200


def test_get_playlist_unknown_session_is_404(client):
    response = client.get("/api/hls/does-not-exist/playlist.m3u8")
    assert response.status_code == 404


def test_stop_session_requires_auth(unauthenticated_client, tmp_path):
    _register_session(tmp_path)
    response = unauthenticated_client.post("/api/hls/sess1/stop")
    assert response.status_code == 401


def test_stop_session_authenticated_tears_down(client, tmp_path):
    session = _register_session(tmp_path)
    # process.returncode is a truthy MagicMock by default (not None), so
    # terminate_process's early-return path is taken - no real process
    # signaling needed for this response-shape/session-removal assertion.
    session.process.returncode = 0

    response = client.post("/api/hls/sess1/stop")

    assert response.status_code == 204
    assert session.session_id not in hls_streaming._sessions
    assert not session.tmp_dir.exists()


# --- new cast-token routes - no cookie/bearer auth, gated by the token itself


def test_get_playlist_for_cast_with_correct_token_returns_200(unauthenticated_client, tmp_path):
    _register_session(tmp_path, cast_token="tok-correct")
    response = unauthenticated_client.get("/api/hls/sess1/tok-correct/playlist.m3u8")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/vnd.apple.mpegurl"


def test_get_segment_for_cast_with_correct_token_returns_200(unauthenticated_client, tmp_path):
    _register_session(tmp_path, cast_token="tok-correct")
    response = unauthenticated_client.get("/api/hls/sess1/tok-correct/segment00000.ts")
    assert response.status_code == 200


def test_get_playlist_for_cast_with_wrong_token_is_404(unauthenticated_client, tmp_path):
    _register_session(tmp_path, cast_token="tok-correct")
    response = unauthenticated_client.get("/api/hls/sess1/tok-wrong/playlist.m3u8")
    assert response.status_code == 404


def test_get_playlist_for_cast_on_session_without_cast_token_is_404(unauthenticated_client, tmp_path):
    """A session created for a native (non-cast) client has cast_token=None -
    no token should ever verify against it."""
    _register_session(tmp_path, cast_token=None)
    response = unauthenticated_client.get("/api/hls/sess1/anything/playlist.m3u8")
    assert response.status_code == 404


def test_get_playlist_for_cast_unknown_session_is_404(unauthenticated_client):
    response = unauthenticated_client.get("/api/hls/does-not-exist/tok/playlist.m3u8")
    assert response.status_code == 404
