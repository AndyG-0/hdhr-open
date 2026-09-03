from __future__ import annotations

import time
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app import hls_streaming
from app.main import app


def test_health_endpoint_ok(tmp_db):
    with TestClient(app) as client:
        response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_lifespan_initializes_db_and_starts_scheduler(tmp_db):
    from app.scheduler import scheduler

    with TestClient(app):
        assert scheduler.running
        assert scheduler.get_job("guide_refresh_hdhomerun_cloud") is not None
        assert scheduler.get_job("guide_refresh_xmltv") is not None
    assert not scheduler.running


# --- CORS: cast-token HLS routes must be fetchable by a Cast receiver's -----
# foreign origin, which can never appear in settings.cors_origins -----------


def _register_cast_session(tmp_path):
    """A Chromecast receiver fetches these routes directly (see
    app/api/hls.py's verify_cast_token) - unlike every other route in this
    app, it isn't the frontend's own origin, so this exercises the
    real app.main middleware stack rather than an isolated router."""
    tmp_dir = tmp_path / "sess"
    tmp_dir.mkdir()
    hls_streaming.playlist_path(tmp_dir).write_bytes(b"#EXTM3U\n#EXTINF:2.0,\nsegment00000.ts\n")
    now = time.time()
    session = hls_streaming.HLSSession(
        session_id="castsess1",
        process=MagicMock(),
        tmp_dir=tmp_dir,
        created_at=now,
        last_request_at=now,
        label="test",
        cast_token="tok123",
    )
    hls_streaming._sessions[session.session_id] = session
    return session


def test_cast_receiver_route_allows_any_origin(tmp_db, tmp_path):
    _register_cast_session(tmp_path)
    try:
        with TestClient(app) as client:
            response = client.get(
                "/api/hls/castsess1/tok123/playlist.m3u8",
                headers={"Origin": "https://receiver.example"},
            )
        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == "*"
    finally:
        hls_streaming._sessions.clear()


def test_cast_receiver_route_preflight_succeeds_for_any_origin(tmp_db, tmp_path):
    _register_cast_session(tmp_path)
    try:
        with TestClient(app) as client:
            response = client.options(
                "/api/hls/castsess1/tok123/playlist.m3u8",
                headers={
                    "Origin": "https://receiver.example",
                    "Access-Control-Request-Method": "GET",
                },
            )
        assert response.status_code == 204
        assert response.headers["access-control-allow-origin"] == "*"
    finally:
        hls_streaming._sessions.clear()


def test_non_cast_route_preflight_still_rejects_foreign_origin(tmp_db):
    # Regression guard: the permissive cast-receiver CORS handling in
    # app/main.py is scoped to only the `/{session_id}/{cast_token}/...`
    # routes - every cookie/bearer-authenticated route must keep enforcing
    # settings.cors_origins exactly as before.
    with TestClient(app) as client:
        response = client.options(
            "/api/hls/sess1/playlist.m3u8",
            headers={
                "Origin": "https://receiver.example",
                "Access-Control-Request-Method": "GET",
            },
        )
    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers
